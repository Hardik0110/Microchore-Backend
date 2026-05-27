from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0002_submission_justification_submission_pasted_chars'),
    ]

    operations = [
        migrations.AlterField(
            model_name='claim',
            name='status',
            field=models.CharField(
                choices=[
                    ('ACTIVE', 'Active'),
                    ('EXPIRED', 'Expired'),
                    ('SUBMITTED', 'Submitted'),
                    ('VOIDED', 'Voided'),
                ],
                db_index=True,
                default='ACTIVE',
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name='submission',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending Review'),
                    ('IN_REVIEW', 'In Review'),
                    ('APPROVED', 'Approved'),
                    ('REJECTED', 'Rejected'),
                    ('HELD', 'Held for Review'),
                ],
                db_index=True,
                default='PENDING',
                max_length=15,
            ),
        ),
        migrations.AddIndex(
            model_name='claim',
            index=models.Index(fields=['task', 'user', 'status'], name='claim_task_user_status_idx'),
        ),
        migrations.AddConstraint(
            model_name='claim',
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=['ACTIVE', 'SUBMITTED']),
                fields=('task', 'user'),
                name='claim_unique_active_per_task_user',
            ),
        ),
    ]
