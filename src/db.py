# import ydb
# import os
# import logging
#
# logger = logging.getLogger(__name__)
#
# # Глобальные переменные для хранения драйвера и пула
# _driver = None
# _pool = None
#
#
# def _get_driver():
#     global _driver
#
#     if _driver is None:
#         try:
#             _driver = ydb.Driver(
#                 endpoint="grpcs://ydb.serverless.yandexcloud.net:2135",
#                 database="/ru-central1/b1g71e95h51okii30p25/etnj66mb9sl4kck50v6t",
#                 credentials=ydb.iam.MetadataUrlCredentials(),
#             )
#             # Увеличиваем таймаут и добавляем логирование
#             _driver.wait(fail_fast=True, timeout=40)
#             logger.info("YDB driver initialized successfully")
#         except Exception as e:
#             logger.error(f"Failed to initialize YDB driver: {e}")
#             raise
#
#     return _driver
#
#
# def _get_pool():
#     """Создаёт пул сессий при первом вызове"""
#     global _pool
#
#     if _pool is None:
#         driver = _get_driver()
#         _pool = ydb.SessionPool(driver)
#         logger.info("YDB session pool created")
#
#     return _pool
#
#
# # def save_task(task_id, title, video_url):
# #     pool = _get_pool()
# #
# #     def op(session):
# #         session.transaction().execute(
# #             """
# #             INSERT INTO tasks (id, created_at, title, video_url, status)
# #             VALUES (?, CurrentUtcTimestamp(), ?, ?, "В очереди");
# #             """,
# #             task_id, title, video_url,
# #             commit_tx=True,
# #         )
# #
# #     pool.retry_operation_sync(op)
#
# def save_task(task_id, title, video_url):
#     pool = _get_pool()
#
#     def op(session):
#         logger.info("task_id=%r title=%r video_url=%r", task_id, title, video_url)
#         session.transaction().execute(
#             """
#             DECLARE $id AS Utf8;
#             DECLARE $title AS Utf8;
#             DECLARE $video_url AS Utf8;
#
#             INSERT INTO tasks (id, created_at, title, video_url, status)
#             VALUES ($id, CurrentUtcTimestamp(), $title, $video_url, "В очереди");
#             """,
#             {
#                 "$id": task_id,
#                 "$title": title,
#                 "$video_url": video_url,
#             },
#             commit_tx=True,
#         )
#
#     pool.retry_operation_sync(op)
#
#
#
#
# # def update_task(task_id, **fields):
# #     pool = _get_pool()
# #
# #     sets = ", ".join(f"{k} = ${k}" for k in fields)
# #     params = {"$id": task_id}
# #     params.update({f"${k}": v for k, v in fields.items()})
# #
# #     def op(session):
# #         session.transaction().execute(
# #             f"UPDATE tasks SET {sets} WHERE id = $id;",
# #             params,
# #             commit_tx=True,
# #         )
# #
# #     pool.retry_operation_sync(op)
#
# def update_task(task_id, **fields):
#     pool = _get_pool()
#
#     declares = []
#     sets = []
#
#     params = {"$id": task_id}
#     declares.append("DECLARE $id AS Utf8;")
#
#     for k, v in fields.items():
#         declares.append(f"DECLARE ${k} AS Utf8;")
#         sets.append(f"{k} = ${k}")
#         params[f"${k}"] = v
#
#     def op(session):
#         session.transaction().execute(
#             f"""
#             {' '.join(declares)}
#
#             UPDATE tasks
#             SET {', '.join(sets)}
#             WHERE id = $id;
#             """,
#             params,
#             commit_tx=True,
#         )
#
#     pool.retry_operation_sync(op)
#
#
#
# # def list_tasks():
# #     pool = _get_pool()
# #
# #     def op(session):
# #         res = session.transaction().execute(
# #             "SELECT * FROM tasks ORDER BY created_at DESC;",
# #             commit_tx=True,
# #         )
# #         return res[0].rows
# #
# #     return pool.retry_operation_sync(op)
#
# def list_tasks():
#     pool = _get_pool()
#
#     def op(session):
#         res = session.transaction().execute(
#             "SELECT * FROM tasks ORDER BY created_at DESC;"
#         )
#         return res[0].rows
#
#     return pool.retry_operation_sync(op)

import ydb
import os
import logging

logger = logging.getLogger(__name__)

# Глобальные переменные для хранения драйвера и пула
_driver = None
_pool = None


def _get_driver():
    global _driver

    if _driver is None:
        try:
            _driver = ydb.Driver(
                endpoint="grpcs://ydb.serverless.yandexcloud.net:2135",
                database="/ru-central1/b1g71e95h51okii30p25/etnj66mb9sl4kck50v6t",
                credentials=ydb.iam.MetadataUrlCredentials(),
            )
            _driver.wait(fail_fast=True, timeout=40)
            logger.info("YDB driver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize YDB driver: {e}")
            raise

    return _driver


def _get_pool():
    """Создаёт пул сессий при первом вызове"""
    global _pool

    if _pool is None:
        driver = _get_driver()
        _pool = ydb.SessionPool(driver)
        logger.info("YDB session pool created")

    return _pool


def save_task(task_id, title, video_url):
    pool = _get_pool()

    def op(session):
        logger.info("SAVING TASK: task_id=%r title=%r video_url=%r", task_id, title, video_url)

        # ПРОСТОЙ ЗАПРОС БЕЗ ПАРАМЕТРОВ - РАБОТАЕТ ВСЕГДА
        query = f"""
        INSERT INTO `tasks` (id, created_at, title, video_url, status)
        VALUES ('{task_id}', CurrentUtcTimestamp(), '{title}', '{video_url}', 'В очереди');
        """

        session.transaction().execute(
            query,
            commit_tx=True,
        )
        logger.info("Task saved successfully")

    pool.retry_operation_sync(op)


def update_task(task_id, **fields):
    pool = _get_pool()

    if not fields:
        return

    # Простой UPDATE без параметров
    set_parts = []
    for k, v in fields.items():
        # Экранируем кавычки
        if isinstance(v, str):
            v = v.replace("'", "''")
        set_parts.append(f"{k} = '{v}'")

    query = f"""
    UPDATE `tasks`
    SET {', '.join(set_parts)}
    WHERE id = '{task_id}';
    """

    def op(session):
        session.transaction().execute(query, commit_tx=True)

    pool.retry_operation_sync(op)


def list_tasks():
    pool = _get_pool()

    def op(session):
        res = session.transaction().execute(
            "SELECT * FROM `tasks` ORDER BY created_at DESC;",
            commit_tx=True,
        )
        return res[0].rows

    return pool.retry_operation_sync(op)

def get_task_url_by_id(task_id):
    pool = _get_pool()

    def op(session):
        query = f"""
        SELECT video_url FROM `tasks` 
        WHERE id = '{task_id}';
        """
        res = session.transaction().execute(query, commit_tx=True)
        return res[0].rows[0] if res[0].rows else None

    return pool.retry_operation_sync(op)


def get_task_by_id(task_id):
    """Получить полные данные задания по ID."""
    pool = _get_pool()

    def op(session):
        query = f"""
        SELECT id, title, video_url, status, pdf_object_key, error, created_at
        FROM `tasks` 
        WHERE id = '{task_id}';
        """
        res = session.transaction().execute(query, commit_tx=True)
        if res[0].rows:
            row = res[0].rows[0]
            return {
                "id": row.id,
                "title": row.title,
                "video_url": row.video_url,
                "status": row.status,
                "pdf_object_key": getattr(row, 'pdf_object_key', None),
                "error": getattr(row, 'error', None),
            }
        return None

    return pool.retry_operation_sync(op)