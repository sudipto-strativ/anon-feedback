from django.urls import path
from . import views

app_name = 'feedback'

urlpatterns = [
    path('', views.feed, name='feed'),
    path('list/', views.list_view, name='list_view'),
    path('post/new/', views.post_create, name='post_create'),
    path('post/<int:pk>/', views.post_detail, name='post_detail'),
    path('post/<int:pk>/vote/', views.vote_post, name='vote_post'),
    path('post/<int:pk>/update-status/', views.update_status, name='update_status'),
    path('comment/<int:pk>/vote/', views.vote_comment, name='vote_comment'),
    path('register/', views.register, name='register'),
]
