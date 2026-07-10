from django.urls import path
from . import views

app_name = 'brain_app'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('concepts/', views.concepts_list, name='concepts_list'),
    path('concepts/<path:rel_path>/', views.concept_detail, name='concept_detail'),
    path('concepts/<path:rel_path>/rename/', views.rename_concept_view, name='rename_concept'),
    path('concepts/<path:rel_path>/delete/', views.delete_concept_view, name='delete_concept'),
    path('ingest/', views.ingest, name='ingest'),
    path('link/', views.link, name='link'),
    path('validate/', views.validate_view, name='validate'),
    path('visualizer/', views.visualizer_view, name='visualizer'),
    path('api/graph/', views.graph_api, name='graph_api'),
    path('change-root/', views.change_root, name='change_root'),
    path('chat/', views.chat_view, name='chat'),
    path('api/chat/', views.chat_message_api, name='chat_message_api'),
    path('rebuild/', views.rebuild_bundle_view, name='rebuild_bundle'),
]
