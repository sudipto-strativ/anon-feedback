"""Strativ Voice routes.

`post_detail` and the action endpoints scoped to a single post route on
the post's `public_id` (UUID) rather than the auto-increment `id`. The
sequential ID is still the primary key internally; it just doesn't
appear in URLs, emails, or Slack messages, where its predictability
would give correlation attackers a small free win.
"""

from django.urls import path
from . import views

app_name = 'feedback'

urlpatterns = [
    path('', views.feed, name='feed'),
    path('list/', views.list_view, name='list_view'),
    path('post/new/', views.post_create, name='post_create'),
    path('post/<uuid:public_id>/', views.post_detail, name='post_detail'),
    path('post/<uuid:public_id>/vote/', views.vote_post, name='vote_post'),
    path('post/<uuid:public_id>/update-status/', views.update_status, name='update_status'),
    path('comment/<int:pk>/vote/', views.vote_comment, name='vote_comment'),
    path('notifications/', views.notifications_list, name='notifications'),
    path('notifications/mark-read/', views.mark_notifications_read, name='mark_notifications_read'),
    path('register/', views.register, name='register'),
]
