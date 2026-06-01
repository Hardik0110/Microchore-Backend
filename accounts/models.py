from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = (
        ('USER', 'Writer'),
        ('REVIEWER', 'Reviewer'),
        ('COMPANY_ADMIN', 'Company Admin'),
        ('PLATFORM_ADMIN', 'Platform Admin'),
    )
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('HELD', 'On Hold'),
        ('BANNED', 'Banned'),
    )
    PAYOUT_METHOD_CHOICES = (
        ('AIRTM', 'Airtm'),
        ('PAYPAL', 'PayPal'),
        ('CRYPTO', 'Crypto'),
    )
    WIZARD_STEP_CHOICES = (
        ('signup', 'Sign up'),
        ('verify-email', 'Verify email'),
        ('welcome', 'Welcome'),
        ('link-account', 'Link account'),
        ('attest', 'Attest'),
        ('tutorial', 'Tutorial'),
        ('first-task', 'First task'),
        ('done', 'Done'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='USER')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='ACTIVE')
    country = models.CharField(max_length=2, blank=True, help_text="ISO 2-letter country code")
    fingerprint_hash = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    payout_method = models.CharField(max_length=15, choices=PAYOUT_METHOD_CHOICES, blank=True, null=True)
    payout_handle = models.CharField(max_length=255, blank=True, null=True, help_text="Payout identifier (stored in plain text; encryption planned)")

    handle = models.CharField(max_length=50, blank=True, default='', help_text="Display name shown in UI")
    email_verified = models.BooleanField(default=False)
    wizard_step = models.CharField(max_length=20, choices=WIZARD_STEP_CHOICES, default='signup')
    starter_approved = models.IntegerField(default=0)
    starter_rejected = models.IntegerField(default=0)
    attested_at = models.DateTimeField(null=True, blank=True)
    tutorial_completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def real_tasks_unlocked(self) -> bool:
        return self.status == 'ACTIVE' and self.starter_approved >= 3

    def __str__(self):
        return f"{self.email or self.username} ({self.role})"


class SocialAccount(models.Model):
    PLATFORM_CHOICES = (
        ('IG', 'Instagram'),
        ('YT', 'YouTube'),
        ('TIKTOK', 'TikTok'),
        ('X', 'Twitter'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='social_accounts')
    platform = models.CharField(max_length=15, choices=PLATFORM_CHOICES)
    handle = models.CharField(max_length=100)
    external_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    follower_count = models.IntegerField(default=0)
    post_count = models.IntegerField(default=0)
    account_age_days = models.IntegerField(default=0)
    last_snapshot_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('platform', 'handle')

    def __str__(self):
        return f"{self.platform}: @{self.handle} ({self.user.email})"


class Hold(models.Model):
    APPEAL_STATUS_CHOICES = (
        ('NONE', 'No Appeal'),
        ('PENDING', 'Pending Review'),
        ('APPROVED', 'Approved (Appeal Won)'),
        ('REJECTED', 'Rejected (Appeal Lost)'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='holds')
    reason = models.TextField()
    started_at = models.DateTimeField(auto_now_add=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    appeal_status = models.CharField(max_length=15, choices=APPEAL_STATUS_CHOICES, default='NONE')
    appeal_text = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Hold for {self.user} (Appeal: {self.appeal_status})"


class Strike(models.Model):
    KIND_CHOICES = (
        ('DELETED_EARLY', 'Comment Deleted Early'),
        ('AI_FLAG', 'AI Usage Flagged'),
        ('MANUAL', 'Manual Strike'),
        ('FRAUD_FLAG', 'Multi-account Fraud'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='strikes')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    submission = models.ForeignKey('submissions.Submission', on_delete=models.SET_NULL, null=True, blank=True, related_name='strikes')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Strike {self.kind} on {self.user}"


class Notification(models.Model):
    KIND_CHOICES = (
        ('submission_approved', 'Submission Approved'),
        ('submission_rejected', 'Submission Rejected'),
        ('real_tasks_unlocked', 'Real Tasks Unlocked'),
        ('promoted_to_reviewer', 'Promoted To Reviewer'),
        ('account_held', 'Account On Hold'),
        ('system', 'System Notice'),
    )

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=400, blank=True, default='')
    link = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"Notification {self.kind} -> {self.recipient.email} ({'read' if self.is_read else 'unread'})"
