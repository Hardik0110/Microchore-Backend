from django.db import models

class SurvivalCheck(models.Model):
    CHECK_TYPE_CHOICES = (
        ('24H', '24-Hour Survival Check'),
        ('48H', '48-Hour Survival Check'),
    )

    submission = models.ForeignKey('submissions.Submission', on_delete=models.CASCADE, related_name='survival_checks')
    check_type = models.CharField(max_length=10, choices=CHECK_TYPE_CHOICES)
    scheduled_at = models.DateTimeField()
    executed_at = models.DateTimeField(null=True, blank=True)
    comment_alive = models.BooleanField(default=True)
    likes_count = models.IntegerField(default=0)
    replies_count = models.IntegerField(default=0)
    comment_text_now = models.TextField(blank=True, null=True)
    delta_from_original = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.check_type} check for Submission {self.submission_id} (Alive: {self.comment_alive})"


class AccountSnapshot(models.Model):
    social_account = models.ForeignKey('accounts.SocialAccount', on_delete=models.CASCADE, related_name='snapshots')
    snapshot_at = models.DateTimeField(auto_now_add=True)
    follower_count = models.IntegerField()
    post_count = models.IntegerField()
    was_alive = models.BooleanField(default=True)
    recent_post_dates = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"Snapshot of @{self.social_account.handle} at {self.snapshot_at}"


class ApiKey(models.Model):
    PLATFORM_CHOICES = (
        ('IG', 'Instagram'),
        ('YT', 'YouTube'),
        ('TIKTOK', 'TikTok'),
        ('X', 'Twitter'),
    )

    platform = models.CharField(max_length=15, choices=PLATFORM_CHOICES)
    key_encrypted = models.TextField(help_text="Encrypted API token credentials")
    daily_quota = models.IntegerField(default=1000)
    used_today = models.IntegerField(default=0)
    last_reset_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.platform} Key ({self.daily_quota - self.used_today} left today)"
