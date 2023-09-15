#!/usr/bin/env python
# -*- coding:utf-8 -*-
# project : server
# filename : urls
# author : ly_13
# date : 6/6/2023
from django.urls import re_path, include
from rest_framework.routers import SimpleRouter

from system.views.announcement import AnnouncementMessage, UserAnnouncement, AnnouncementUserReadMessage
from system.views.auth import TempTokenView, RegisterView, LoginView, LogoutView, RefreshTokenView, CaptchaView
from system.views.menu import UserRoutesView, MenuView
from system.views.notification import NotifyMessage, UserNotice
from system.views.operationlog import OperationLogView
from system.views.role import RoleView
from system.views.upload import UploadView
from system.views.user import UserView
from system.views.userinfo import UserInfoView

router = SimpleRouter(False)

no_auth_url = [
    re_path('^register$', RegisterView.as_view(), name='register'),
    re_path('^login$', LoginView.as_view(), name='login'),
    re_path('^auth/token$', TempTokenView.as_view(), name='temp_token'),
    re_path('^auth/captcha$', CaptchaView.as_view(), name='captcha'),
    re_path('^captcha/', include('captcha.urls')),
]

auth_url = [
    re_path('^logout$', LogoutView.as_view(), name='logout'),
    re_path('^refresh$', RefreshTokenView.as_view(), name='refresh'),
    re_path('^upload$', UploadView.as_view(), name='upload'),
]

menu_url = [
    re_path('^routes$', UserRoutesView.as_view(), name='user_routes'),
]

# 个人用户信息
router.register('userinfo', UserInfoView, basename='userinfo')

# 系统设置相关路由
router.register('user', UserView, basename='user')
router.register('menu', MenuView, basename='menu')
router.register('role', RoleView, basename='role')
router.register('operation', OperationLogView, basename='operation_log')

router.register('notify', NotifyMessage, basename='notify')
router.register('announcement', AnnouncementMessage, basename='announcement')
router.register('read/announcement', AnnouncementUserReadMessage, basename='read_announcement')

router.register('notice', UserNotice, basename='notice')
router.register('announce', UserAnnouncement, basename='announce')

urlpatterns = no_auth_url + auth_url + menu_url + router.get_urls()
