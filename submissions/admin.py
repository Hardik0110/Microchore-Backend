from django.contrib import admin
from .models import Claim, Submission

class ClaimAdmin(admin.ModelAdmin):
    list_display = ('id', 'task', 'user', 'status', 'claimed_at', 'expires_at')
    list_filter = ('status', 'claimed_at')
    search_fields = ('user__email', 'user__username', 'task__keyword')

class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'claim', 'comment_account_handle', 'status', 'rating_final', 'base_payout', 'submitted_at')
    list_filter = ('status', 'proof_type')
    search_fields = ('comment_account_handle', 'comment_url', 'comment_text_snapshot')

admin.site.register(Claim, ClaimAdmin)
admin.site.register(Submission, SubmissionAdmin)
