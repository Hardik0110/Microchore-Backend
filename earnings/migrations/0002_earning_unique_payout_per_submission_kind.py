from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('earnings', '0001_initial'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='earning',
            constraint=models.UniqueConstraint(
                condition=models.Q(submission__isnull=False) & models.Q(kind__in=['BASE', 'BONUS']),
                fields=('submission', 'kind'),
                name='earning_unique_payout_per_submission_kind',
            ),
        ),
    ]
