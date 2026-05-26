from django.db import models
from django.conf import settings

class Claim(models.Model):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('SUBMITTED', 'Submitted'),
        ('VOIDED', 'Voided'),
    )

    task = models.ForeignKey('projects.Task', on_delete=models.CASCADE, related_name='claims')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='claims')
    claimed_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='ACTIVE')

    def __str__(self):
        return f"Claim by {self.user} on {self.task}"


class Submission(models.Model):
    PROOF_CHOICES = (
        ('URL', 'URL Verification'),
        ('SCREENSHOT', 'Screenshot Proof'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending Review'),
        ('IN_REVIEW', 'In Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('HELD', 'Held for Review'),
    )

    claim = models.OneToOneField(Claim, on_delete=models.CASCADE, related_name='submission')
    comment_url = models.URLField()
    comment_text_snapshot = models.TextField()
    comment_account_handle = models.CharField(max_length=100)
    proof_type = models.CharField(max_length=15, choices=PROOF_CHOICES, default='URL')
    screenshot_url = models.URLField(blank=True, null=True)
    paste_event_count = models.IntegerField(default=0)
    pasted_chars = models.IntegerField(default=0)
    keypress_count = models.IntegerField(default=0)
    time_to_compose_seconds = models.IntegerField(default=0)
    attestation_signed = models.BooleanField(default=False)
    ai_likelihood_score = models.DecimalField(max_digits=5, decimal_places=4, default=0.0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    rating_final = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    justification = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    base_payout = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    bonus_payout = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)

    def __str__(self):
        return f"Submission by {self.claim.user} ({self.status})"
