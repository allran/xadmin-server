#!/usr/bin/env python
# -*- coding:utf-8 -*-
# project : xadmin_server
# filename : signal_handler
# author : ly_13
# date : 6/29/2023
import logging

from celery import subtask
from celery.signals import worker_ready, worker_shutdown, after_setup_logger
from django.core.cache import cache
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult

from common.base.utils import remove_file
from common.celery.decorator import get_after_app_ready_tasks, get_after_app_shutdown_clean_tasks
from common.celery.logger import CeleryThreadTaskFileHandler
from common.celery.utils import get_celery_task_log_path
from common.utils import get_logger

logger = get_logger(__name__)
safe_str = lambda x: x


@worker_ready.connect
def on_app_ready(sender=None, headers=None, **kwargs):
    if cache.get("CELERY_APP_READY", 0) == 1:
        return
    cache.set("CELERY_APP_READY", 1, 10)
    tasks = get_after_app_ready_tasks()
    logger.debug("Work ready signal recv")
    logger.debug("Start need start task: [{}]".format(", ".join(tasks)))
    for task in tasks:
        periodic_task = PeriodicTask.objects.filter(task=task).first()
        if periodic_task and not periodic_task.enabled:
            logger.debug("Periodic task [{}] is disabled!".format(task))
            continue
        subtask(task).delay()


@worker_shutdown.connect
def after_app_shutdown_periodic_tasks(sender=None, **kwargs):
    if cache.get("CELERY_APP_SHUTDOWN", 0) == 1:
        return
    cache.set("CELERY_APP_SHUTDOWN", 1, 10)
    tasks = get_after_app_shutdown_clean_tasks()
    logger.debug("Worker shutdown signal recv")
    logger.debug("Clean period tasks: [{}]".format(', '.join(tasks)))
    PeriodicTask.objects.filter(name__in=tasks).delete()


@receiver(pre_delete, sender=TaskResult)
def delete_file_handler(sender, **kwargs):
    # 清理任务记录，同时并清理日志文件
    instance = kwargs.get('instance')
    if instance:
        task_id = instance.task_id
        if task_id:
            log_path = get_celery_task_log_path(task_id)
            remove_file(log_path)


@after_setup_logger.connect
def on_after_setup_logger(sender=None, logger=None, loglevel=None, format=None, **kwargs):
    if not logger:
        return
    task_handler = CeleryThreadTaskFileHandler()
    task_handler.setLevel(loglevel)
    formatter = logging.Formatter(format)
    task_handler.setFormatter(formatter)
    logger.addHandler(task_handler)
