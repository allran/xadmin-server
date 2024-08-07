#!/usr/bin/env python
# -*- coding:utf-8 -*-
# project : server
# filename : auth
# author : ly_13
# date : 6/6/2023
import hashlib
import time

from django.conf import settings
from django.contrib import auth
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView
from user_agents import parse

from common.cache.storage import BlackAccessTokenCache
from common.core.response import ApiResponse
from common.core.throttle import RegisterThrottle, LoginThrottle
from common.utils.request import get_request_ip, get_browser, get_os
from common.utils.token import make_token
from system.models import UserInfo, DeptInfo, UserLoginLog
from system.utils.captcha import CaptchaAuth
from system.utils.security import check_password_rules, LoginBlockUtil, LoginIpBlockUtil, get_password_check_rules
from system.utils.serializer import UserLoginLogSerializer
from system.utils.view import get_request_ident, get_username_password, \
    get_token_lifetime, check_is_block, check_token_and_captcha


def save_login_log(request, login_type=UserLoginLog.LoginTypeChoices.USERNAME, status=True):
    data = {
        'ipaddress': get_request_ip(request),
        'browser': get_browser(request),
        'system': get_os(request),
        'status': status,
        'agent': str(parse(request.META['HTTP_USER_AGENT'])),
        'login_type': login_type
    }
    serializer = UserLoginLogSerializer(data=data, request=request, all_fields=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()


class TempTokenView(APIView):
    """获取临时token"""
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        token = make_token(get_request_ident(request), time_limit=600, force_new=True).encode('utf-8')
        return ApiResponse(token=token)


class CaptchaView(APIView):
    """获取验证码"""
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return ApiResponse(**CaptchaAuth().generate())


class RegisterView(APIView):
    """用户注册"""
    permission_classes = []
    authentication_classes = []
    throttle_classes = [RegisterThrottle]

    def post(self, request, *args, **kwargs):
        if not settings.SECURITY_REGISTER_ACCESS_ENABLED:
            return ApiResponse(code=1001, detail=_("Registration forbidden"))

        client_id, token = check_token_and_captcha(request, settings.SECURITY_REGISTER_TEMP_TOKEN_ENABLED,
                                                   settings.SECURITY_REGISTER_CAPTCHA_ENABLED)

        channel = request.data.get('channel', 'default')
        username, password = get_username_password(settings.SECURITY_REGISTER_ENCRYPTED_ENABLED, request, token)
        if not check_password_rules(password):
            return ApiResponse(code=1001, detail=_("Password does not match security rules"))
        if UserInfo.objects.filter(username=username).count():
            return ApiResponse(code=1002, detail=_("The username already exists, please try another one"))

        user = auth.authenticate(username=username, password=password)
        update_fields = ['last_login']
        if not user:
            user = UserInfo.objects.create_user(username=username, password=password, first_name=username,
                                                nickname=username)
            if channel and user:
                dept = DeptInfo.objects.filter(is_active=True, auto_bind=True, code=channel).first()
                if not dept:
                    dept = DeptInfo.objects.filter(is_active=True, auto_bind=True).first()
                if dept:
                    user.dept = dept
                    user.dept_belong = dept
                    update_fields.extend(['dept_belong', 'dept'])

        refresh = RefreshToken.for_user(user)
        result = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        user.last_login = timezone.now()
        user.save(update_fields=update_fields)
        result.update(**get_token_lifetime(user))
        request.user = user
        save_login_log(request)
        return ApiResponse(data=result)

    def get(self, request, *args, **kwargs):
        config = {
            'access': settings.SECURITY_REGISTER_ACCESS_ENABLED,
            'captcha': settings.SECURITY_REGISTER_CAPTCHA_ENABLED,
            'token': settings.SECURITY_REGISTER_TEMP_TOKEN_ENABLED,
            'encrypted': settings.SECURITY_REGISTER_ENCRYPTED_ENABLED,
            'password': get_password_check_rules(request.user)
        }
        return ApiResponse(data=config)

class LoginView(TokenObtainPairView):
    """用户登录"""
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        if not settings.SECURITY_LOGIN_ACCESS_ENABLED:
            return ApiResponse(code=1001, detail=_("Login forbidden"))

        ipaddr = get_request_ip(request)
        client_id, token = check_token_and_captcha(request, settings.SECURITY_LOGIN_TEMP_TOKEN_ENABLED,
                                                   settings.SECURITY_LOGIN_CAPTCHA_ENABLED)

        username, password = get_username_password(settings.SECURITY_LOGIN_ENCRYPTED_ENABLED, request, token)

        check_is_block(username, ipaddr)

        login_block_util = LoginBlockUtil(username, ipaddr)
        login_ip_block = LoginIpBlockUtil(ipaddr)

        serializer = self.get_serializer(data={'username': username, 'password': password})
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            request.user = UserInfo.objects.filter(username=request.data.get('username')).first()
            save_login_log(request, status=False)
            login_block_util.incr_failed_count()
            login_ip_block.set_block_if_need()

            times_remainder = login_block_util.get_remainder_times()
            if times_remainder > 0:
                detail = _(
                    "The username or password you entered is incorrect, "
                    "please enter it again. "
                    "You can also try {times_try} times "
                    "(The account will be temporarily locked for {block_time} minutes)"
                ).format(times_try=times_remainder, block_time=settings.SECURITY_LOGIN_LIMIT_TIME)
            else:
                detail = _("The account has been locked (please contact admin to unlock it or try"
                           " again after {} minutes)").format(settings.SECURITY_LOGIN_LIMIT_TIME)
            return ApiResponse(code=9999, detail=detail)
        data = serializer.validated_data
        data.update(get_token_lifetime(serializer.user))
        request.user = serializer.user
        save_login_log(request)

        login_block_util.clean_failed_count()
        login_ip_block.clean_block_if_need()

        return ApiResponse(data=data)

    def get(self, request, *args, **kwargs):
        config = {
            'access': settings.SECURITY_LOGIN_ACCESS_ENABLED,
            'captcha': settings.SECURITY_LOGIN_CAPTCHA_ENABLED,
            'token': settings.SECURITY_LOGIN_TEMP_TOKEN_ENABLED,
            'encrypted': settings.SECURITY_LOGIN_ENCRYPTED_ENABLED,
            'lifetime': settings.SIMPLE_JWT.get('REFRESH_TOKEN_LIFETIME').days,
            'reset': settings.SECURITY_RESET_PASSWORD_ACCESS_ENABLED
        }
        return ApiResponse(data=config)

class RefreshTokenView(TokenRefreshView):
    """刷新Token"""

    def post(self, request, *args, **kwargs):
        data = super().post(request, *args, **kwargs).data
        data.update(get_token_lifetime(request.user))
        return ApiResponse(data=data)


class LogoutView(APIView):
    """用户登出"""

    def post(self, request):
        """
        登出账户，并且将账户的access 和 refresh token 加入黑名单
        """
        payload = request.auth.payload
        exp = payload.get('exp')
        user_id = payload.get('user_id')
        timeout = exp - time.time()
        BlackAccessTokenCache(user_id, hashlib.md5(request.auth.token).hexdigest()).set_storage_cache(1, timeout)
        if request.data.get('refresh'):
            try:
                token = RefreshToken(request.data.get('refresh'))
                token.blacklist()
            except Exception as e:
                pass
        return ApiResponse()


class PasswordRulesView(APIView):
    permission_classes = []

    def get(self, request):
        return ApiResponse(data={"password_rules": get_password_check_rules(request.user)})
