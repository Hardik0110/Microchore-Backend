from django.db import models

class Company(models.Model):
    name = models.CharField(max_length=255)
    registration_details = models.JSONField(default=dict, blank=True, help_text="Registration payload (e.g. ABN, address)")

    class Meta:
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


class Project(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('PAUSED', 'Paused'),
        ('COMPLETE', 'Complete'),
    )
    CADENCE_CHOICES = (
        ('WEEKLY', 'Weekly'),
        ('BIWEEKLY', 'Biweekly'),
        ('MONTHLY', 'Monthly'),
    )
    PAYOUT_METHOD_CHOICES = (
        ('AIRTM', 'Airtm'),
        ('PAYPAL', 'PayPal'),
        ('CRYPTO', 'Crypto'),
        ('ANY', 'Any'),
    )
    STRICTNESS_CHOICES = (
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    )
    TONE_CHOICES = (
        ('lifestyle', 'Lifestyle'),
        ('product', 'Product'),
        ('story', 'Story'),
        ('disagreement', 'Disagreement'),
        ('brand', 'Brand'),
    )

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255)
    is_starter = models.BooleanField(default=False, help_text="Practice project shown to fresh users")
    tone = models.CharField(max_length=20, choices=TONE_CHOICES, default='lifestyle')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='DRAFT')
    brief_md = models.TextField(help_text="Markdown campaign brief guidelines")
    tone_guidance = models.TextField(blank=True, help_text="Specific tone directives")
    target_post_url_default = models.URLField(blank=True, null=True)
    keyword_default = models.CharField(max_length=100, blank=True, null=True)
    pay_rate_per_approved_task = models.DecimalField(max_digits=10, decimal_places=4)
    payout_cadence = models.CharField(max_length=15, choices=CADENCE_CHOICES, default='WEEKLY')
    payout_method_required = models.CharField(max_length=15, choices=PAYOUT_METHOD_CHOICES, default='ANY')
    payout_min_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=5.0)
    terms_md = models.TextField(help_text="Markdown terms shown to writers before claim")
    ai_detection_strictness = models.CharField(max_length=15, choices=STRICTNESS_CHOICES, default='MEDIUM')
    credibility_thresholds = models.JSONField(default=dict, blank=True, help_text="Minimum followers/posts requirements")
    created_at = models.DateTimeField(auto_now_add=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.status})"


class Task(models.Model):
    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('EXHAUSTED', 'Exhausted'),
        ('EXPIRED', 'Expired'),
    )

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='OPEN')
    target_post_url = models.URLField(blank=True, null=True, help_text="Specific target post (defaults to project's default)")
    keyword = models.CharField(max_length=100, blank=True, null=True, help_text="Specific keyword (defaults to project's default)")
    remaining_count = models.IntegerField(default=1)
    total_count = models.IntegerField(default=1)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Task in {self.project.name} (Keyword: {self.keyword or self.project.keyword_default})"
