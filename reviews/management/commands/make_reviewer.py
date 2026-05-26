from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from reviews.models import ReviewerStats


class Command(BaseCommand):
    help = 'Grant reviewer status to a user. Creates or updates their ReviewerStats row.'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Email of the user to make a reviewer')
        parser.add_argument(
            '--tier',
            type=str,
            default='T1',
            choices=['T1', 'T2', 'ADMIN'],
            help='Reviewer tier (default: T1)',
        )
        parser.add_argument(
            '--multiplier',
            type=str,
            default='1.0',
            help='Pay multiplier (default: 1.0)',
        )

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        tier = options['tier']
        try:
            multiplier = Decimal(options['multiplier'])
        except Exception:
            raise CommandError(f'Invalid multiplier: {options["multiplier"]}')

        User = get_user_model()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f'No user with email {email}')

        stats, created = ReviewerStats.objects.update_or_create(
            user=user,
            defaults={'tier': tier, 'current_pay_multiplier': multiplier},
        )
        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} ReviewerStats for {email}: tier={tier}, multiplier={multiplier}'
        ))
