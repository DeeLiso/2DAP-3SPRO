from django.contrib.auth import views as auth_views
from django.urls import path
from django.shortcuts import redirect
from django.views.static import serve
from django.conf import settings

from . import views

urlpatterns = [
    path('app/admin/', views.react_app, {'screen': 'admin'}, name='react_admin'),
    path('app/', views.react_app, {'screen': 'gateway'}, name='react_gateway'),
    path('robots.txt', views.robots_txt, name='robots'),
    path('sw.js', lambda r: serve(r, 'sw.js', document_root=str(settings.BASE_DIR / 'twodapp' / 'static')), name='service_worker'),
    path('login/', views.react_login, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', lambda r: redirect('/login/'), name='home'),
    path('bet/', views.index, name='index'),
    path('records/', views.records_page, name='records'),
    path('bet/records/', views.bettor_records_page, name='bettor_records'),
    path('limit/', views.limit_page, name='limit'),
    path('ledger/', views.ledger_page, name='ledger'),
    path('api/parse', views.api_parse, name='api_parse'),
    path('api/live', views.api_live, name='api_live'),
    path('api/set_global_limit', views.api_set_global_limit, name='api_set_global_limit'),
    path('api/set_specific_limit', views.api_set_specific_limit, name='api_set_specific_limit'),
    path('api/delete_specific_limit', views.api_delete_specific_limit, name='api_delete_specific_limit'),
    path('api/save_meta', views.api_save_meta, name='api_save_meta'),
    path('api/clear_all', views.api_clear_all, name='api_clear_all'),
    path('api/local_store_info', views.api_local_store_info, name='api_local_store_info'),
    path('api/local_store_delete', views.api_local_store_delete, name='api_local_store_delete'),
    path('api/local_store_download', views.api_local_store_download, name='api_local_store_download'),
    path('api/delete_logs', views.api_delete_logs, name='api_delete_logs'),
    path('api/toggle_cancel', views.api_toggle_cancel, name='api_toggle_cancel'),
    path('api/edit_logs', views.api_edit_logs, name='api_edit_logs'),
    path('api/create_bettor', views.api_create_bettor, name='api_create_bettor'),
    path('api/list_bettors', views.api_list_bettors, name='api_list_bettors'),
    path('api/delete_bettor', views.api_delete_bettor, name='api_delete_bettor'),
    path('api/edit_bettor', views.api_edit_bettor, name='api_edit_bettor'),
    path('api/list_groups', views.api_list_groups, name='api_list_groups'),
    path('api/create_group', views.api_create_group, name='api_create_group'),
    path('api/edit_group', views.api_edit_group, name='api_edit_group'),
    path('api/delete_group', views.api_delete_group, name='api_delete_group'),
    path('bet/login/', views.bettor_login_page, name='bettor_login'),
    path('bet/manage_bettors/', views.manage_bettors_page, name='manage_bettors'),
    path('operator/', views.operator_panel_page, name='operator'),
    path('api/list_operators', views.api_list_operators, name='api_list_operators'),
    path('api/create_operator', views.api_create_operator, name='api_create_operator'),
    path('api/edit_operator', views.api_edit_operator, name='api_edit_operator'),
    path('api/reset_operator_password', views.api_reset_operator_password, name='api_reset_operator_password'),
    path('api/delete_operator', views.api_delete_operator, name='api_delete_operator'),
    path('api/bettor_login', views.api_bettor_login, name='api_bettor_login'),
    path('api/bettor_profile', views.api_bettor_profile, name='api_bettor_profile'),
    path('chat/', views.chat_page, name='chat'),
    path('bet/chat/', views.bettor_chat_page, name='bettor_chat'),
    path('settings/', views.settings_page, name='settings'),
    path('bet/settings/', views.bettor_settings_page, name='bettor_settings'),
    path('api/chat/send', views.api_chat_send, name='api_chat_send'),
    path('api/chat/poll', views.api_chat_poll, name='api_chat_poll'),
    path('api/chat/clear', views.api_chat_clear, name='api_chat_clear'),
    path('api/chat/pin', views.api_chat_pin, name='api_chat_pin'),
    path('api/chat/react', views.api_chat_react, name='api_chat_react'),
    path('api/chat/upload_photo', views.api_chat_upload_photo, name='api_chat_upload_photo'),
    path('api/chat/upload_audio', views.api_chat_upload_audio, name='api_chat_upload_audio'),
    path('api/chat/edit', views.api_chat_edit, name='api_chat_edit'),
    path('api/chat/delete', views.api_chat_delete, name='api_chat_delete'),
    path('api/chat/typing', views.api_chat_typing, name='api_chat_typing'),
    path('api/change_password', views.api_change_password, name='api_change_password'),
    path('api/bettor/change_password', views.api_bettor_change_password, name='api_bettor_change_password'),
]

if settings.DEBUG:
    urlpatterns += [
        path('media/<path:path>', lambda r, path: serve(r, path, document_root=str(settings.MEDIA_ROOT))),
    ]
