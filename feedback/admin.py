from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserProfile, Post, Comment, Vote, NotificationEmail, SlackConfig


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at')
    search_fields = ('content', 'author__username')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'post', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('content', 'author__username')
    readonly_fields = ('created_at',)


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'vote_type', 'post', 'comment', 'created_at')
    list_filter = ('vote_type', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)


@admin.register(NotificationEmail)
class NotificationEmailAdmin(admin.ModelAdmin):
    list_display = ('email', 'notify_on_new_post', 'notify_on_new_comment', 'created_at')
    list_editable = ('notify_on_new_post', 'notify_on_new_comment')
    readonly_fields = ('created_at',)


@admin.register(SlackConfig)
class SlackConfigAdmin(admin.ModelAdmin):
    list_display = ('channel_name', 'webhook_url', 'is_active')
    list_filter = ('is_active',)
