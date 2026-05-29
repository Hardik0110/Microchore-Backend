from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_notification'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(
                Lower('email'),
                name='accounts_user_email_lower_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(
                Lower('payout_handle'),
                condition=models.Q(payout_handle__isnull=False) & ~models.Q(payout_handle=''),
                name='accounts_user_payout_handle_lower_unique',
            ),
        ),
    ]
