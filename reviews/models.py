from django.db import models
from django.conf import settings

class Review(models.Model):
    submission = models.ForeignKey('submissions.Submission', on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(help_text="Anchored quality rating (1 to 5 stars)")
    justification_text = models.TextField(help_text="Mandatory textual justification for the rating")
    feels_ai_flag = models.BooleanField(default=False, help_text="Ticked if the comment reads like a chatbot output")
    time_taken_seconds = models.IntegerField(default=0)
    is_authoritative = models.BooleanField(default=False, help_text="True if this review was the authoritative decision maker")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # BE-028: a reviewer can submit at most one review per submission.
            # Defends the consensus count and REVIEW_PAY against double-submit races.
            models.UniqueConstraint(
                fields=['submission', 'reviewer'],
                name='review_unique_per_submission_reviewer',
            ),
        ]

    def __str__(self):
        return f"Review by {self.reviewer} on {self.submission.id} (Rating: {self.rating})"


class Bundle(models.Model):
    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('EXPIRED', 'Expired'),
    )

    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bundles')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    submissions = models.ManyToManyField('submissions.Submission', related_name='bundles')

    def __str__(self):
        return f"Bundle {self.id} for {self.reviewer} ({self.status})"


class ReviewerStats(models.Model):
    TIER_CHOICES = (
        ('T1', 'Tier 1'),
        ('T2', 'Tier 2'),
        ('ADMIN', 'Admin Reviewer'),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviewer_stats')
    tier = models.CharField(max_length=15, choices=TIER_CHOICES, default='T1')
    rolling_accuracy_score = models.DecimalField(max_digits=5, decimal_places=2, default=100.0)
    reviews_completed = models.IntegerField(default=0)
    current_pay_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)
    daily_review_count = models.IntegerField(default=0)
    last_review_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Reviewer Stats"

    def __str__(self):
        return f"Stats for {self.user.email} (Tier: {self.tier})"
