from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from feedback import views as feedback_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', feedback_views.feed, name='feed'),
    path('list/', feedback_views.list_view, name='list_view'),
    path('post/new/', feedback_views.post_create, name='post_create'),
    path('post/<int:pk>/', feedback_views.post_detail, name='post_detail'),
    path('post/<int:pk>/vote/', feedback_views.vote_post, name='vote_post'),
    path('post/<int:pk>/update-status/', feedback_views.update_status, name='update_status'),
    path('comment/<int:pk>/vote/', feedback_views.vote_comment, name='vote_comment'),
    path('register/', feedback_views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='feedback/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
