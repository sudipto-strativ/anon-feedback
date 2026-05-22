"""Strativ Voice admin — hardened to keep authorship invisible.

The product promise is anonymous feedback, so the admin panel must not
become a back-door deanonymiser. Concretely:

- PostAdmin and CommentAdmin never expose any author/user column. They
  can't, anyway — those FKs were dropped in migration 0012. The list
  columns below are deliberately content/status/timing only.
- VoteAdmin, FavouriteAdmin, and SubscriptionAdmin still have `user`
  columns because those are user *actions* (voted / bookmarked /
  followed), not posting/commenting. We gate them behind superuser-only
  so day-to-day staff can't browse "who voted on what."
- The Django User admin is similarly gated to superusers. Role
  assignment is meant to flow through the `assign_role` management
  command, not the UI.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    Comment,
    CommentImage,
    NotificationEmail,
    Post,
    PostAttachment,
    SlackConfig,
    Subscription,
    UserProfile,
    Vote,
)


class _SuperuserOnlyMixin:
    """Hide the model entirely from non-superuser staff.

    These ModelAdmins expose user→post links (Vote, Favourite, Subscription)
    or user identity (User). Day-to-day staff should never need them.
    """

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_add_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


class UserAdmin(_SuperuserOnlyMixin, BaseUserAdmin):
    inlines = [UserProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    """No author column or search; there is no author to expose."""

    list_display = ('id', 'status', 'target_role', 'created_at', 'updated_at')
    list_filter = ('status', 'target_role', 'created_at')
    search_fields = ('content',)
    readonly_fields = ('public_id', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """`role` is shown so HR can triage by role *category*, not by user."""

    list_display = ('id', 'post', 'role', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('content',)
    readonly_fields = ('created_at',)


@admin.register(Vote)
class VoteAdmin(_SuperuserOnlyMixin, admin.ModelAdmin):
    list_display = ('id', 'user', 'vote_type', 'post', 'comment', 'created_at')
    list_filter = ('vote_type', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)


@admin.register(Subscription)
class SubscriptionAdmin(_SuperuserOnlyMixin, admin.ModelAdmin):
    list_display = ('id', 'user', 'post')
    search_fields = ('user__username',)


@admin.register(NotificationEmail)
class NotificationEmailAdmin(admin.ModelAdmin):
    list_display = ('email', 'notify_on_new_post', 'notify_on_new_comment', 'created_at')
    list_editable = ('notify_on_new_post', 'notify_on_new_comment')
    readonly_fields = ('created_at',)


@admin.register(SlackConfig)
class SlackConfigAdmin(admin.ModelAdmin):
    list_display = ('channel_name', 'webhook_url', 'is_active')
    list_filter = ('is_active',)


@admin.register(PostAttachment)
class PostAttachmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'filename', 'uploaded_at')
    readonly_fields = ('uploaded_at',)

    def filename(self, obj):
        return obj.filename


@admin.register(CommentImage)
class CommentImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'comment', 'uploaded_at')
    readonly_fields = ('uploaded_at',)
