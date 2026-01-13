from django.urls import path
from . import views

urlpatterns = [
    path('', views.monitoring_view, name='monitoring_view'),
    path('api/data/', views.fetch_data_api, name='fetch_data'),
    path('api/trends/', views.fetch_trends_api, name='fetch_trends'),
    path('api/current-risk/', views.get_current_risk_status, name='get_current_risk_status'),
    path('flood-record/', views.flood_record_form, name='flood_record_form'),
    path('flood-record/edit/<int:record_id>/', views.flood_record_edit, name='flood_record_edit'),
    path('flood-record/delete/<int:record_id>/', views.flood_record_delete, name='flood_record_delete'),
    path('benchmark-settings/', views.benchmark_settings_view, name='benchmark_settings'),
    path('export-trends/', views.export_trends, name='export_trends'),
    path('export-flood-records/', views.export_flood_records, name='export_flood_records'),
]