from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_account_constraints'),
    ]

    operations = [
        migrations.AddField(
            model_name='socialaccount',
            name='external_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
    ]
