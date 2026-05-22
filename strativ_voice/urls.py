from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from feedback import views as feedback_views

# Post-scoped endpoints use the post's UUID public_id rather than the
# sequential PK. The sequential ID would let a correlation attacker
# count posts ("oh, only post #42 exists, and it was made today") which
# is a side-channel we want closed alongside the author-FK removal.
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', feedback_views.feed, name='feed'),
    path('list/', feedback_views.list_view, name='list_view'),
    path('post/new/', feedback_views.post_create, name='post_create'),
    path('post/<uuid:public_id>/', feedback_views.post_detail, name='post_detail'),
    path('post/<uuid:public_id>/vote/', feedback_views.vote_post, name='vote_post'),
    path('post/<uuid:public_id>/update-status/', feedback_views.update_status, name='update_status'),
    path('post/<uuid:public_id>/favourite/', feedback_views.toggle_favourite, name='toggle_favourite'),
    path('comment/<int:pk>/vote/', feedback_views.vote_comment, name='vote_comment'),
    path('favourites/', feedback_views.favourites_feed, name='favourites'),
    path('notifications/', feedback_views.notifications_list, name='notifications'),
    path('notifications/mark-read/', feedback_views.mark_notifications_read, name='mark_notifications_read'),
    path('register/', feedback_views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='feedback/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
