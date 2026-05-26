from django.contrib import admin
from .models import SurvivalCheck, AccountSnapshot, ApiKey

class SurvivalCheckAdmin(admin.ModelAdmin):
    list_display = ('id', 'submission', 'check_type', 'scheduled_at', 'executed_at', 'comment_alive')
    list_filter = ('check_type', 'comment_alive')

class AccountSnapshotAdmin(admin.ModelAdmin):
    list_display = ('id', 'social_account', 'snapshot_at', 'follower_count', 'post_count', 'was_alive')
    list_filter = ('was_alive',)

class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ('platform', 'daily_quota', 'used_today', 'is_active', 'last_reset_at')
    list_filter = ('platform', 'is_active')

admin.site.register(SurvivalCheck, SurvivalCheckAdmin)
admin.site.register(AccountSnapshot, AccountSnapshotAdmin)
admin.site.register(ApiKey, ApiKeyAdmin)
