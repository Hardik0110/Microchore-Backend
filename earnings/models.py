from django.db import models
from django.conf import settings

class PayoutBatch(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft Report'),
        ('EXPORTED', 'Exported to Company'),
        ('CONFIRMED_PAID', 'Confirmed Paid'),
    )

    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='payout_batches')
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=4)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    exported_at = models.DateTimeField(null=True, blank=True)
    sent_to_company_at = models.DateTimeField(null=True, blank=True)
    confirmation_received_at = models.DateTimeField(null=True, blank=True)
    report_url = models.URLField(blank=True, null=True, help_text="R2 CSV payout export spreadsheet link")

    class Meta:
        verbose_name_plural = "Payout Batches"

    def __str__(self):
        return f"Batch {self.id} for {self.project.name} (Status: {self.status})"


class Earning(models.Model):
    KIND_CHOICES = (
        ('BASE', 'Base Payout'),
        ('BONUS', 'Engagement Bonus'),
        ('REFERRAL', 'Referral Reward'),
        ('REVIEW_PAY', 'Review Compensation'),
    )
    STATUS_CHOICES = (
        ('PENDING_PAYOUT', 'Pending Payout'),
        ('EXPORTED', 'Exported in Batch'),
        ('PAID', 'Paid Successfully'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='earnings')
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='earnings')
    submission = models.ForeignKey('submissions.Submission', on_delete=models.CASCADE, null=True, blank=True, related_name='earnings')
    amount = models.DecimalField(max_digits=10, decimal_places=4)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_PAYOUT')
    payout_batch = models.ForeignKey(PayoutBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='earnings')
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Earning of {self.amount} for {self.user.email} (Kind: {self.kind})"
