from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
from monitoring.models import RainfallData, WeatherData, TideLevelData


class Command(BaseCommand):
    help = 'Clear all dummy monitoring data before today (keeps today\'s records and all FloodRecord data)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion without prompting',
        )

    def handle(self, *args, **options):
        # Get today's date at midnight (start of day)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.WARNING('CLEAR DUMMY DATA COMMAND'))
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write('')
        
        # Count records before deletion
        rainfall_count = RainfallData.objects.filter(timestamp__lt=today_start).count()
        weather_count = WeatherData.objects.filter(timestamp__lt=today_start).count()
        tide_count = TideLevelData.objects.filter(timestamp__lt=today_start).count()
        
        rainfall_today = RainfallData.objects.filter(timestamp__gte=today_start).count()
        weather_today = WeatherData.objects.filter(timestamp__gte=today_start).count()
        tide_today = TideLevelData.objects.filter(timestamp__gte=today_start).count()
        
        self.stdout.write(f'Current date: {today_start.strftime("%B %d, %Y")}')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Records to be DELETED (before today):'))
        self.stdout.write(f'  • RainfallData: {rainfall_count} records')
        self.stdout.write(f'  • WeatherData: {weather_count} records')
        self.stdout.write(f'  • TideLevelData: {tide_count} records')
        self.stdout.write(f'  TOTAL: {rainfall_count + weather_count + tide_count} records')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Records to be KEPT (today onwards):'))
        self.stdout.write(f'  • RainfallData: {rainfall_today} records')
        self.stdout.write(f'  • WeatherData: {weather_today} records')
        self.stdout.write(f'  • TideLevelData: {tide_today} records')
        self.stdout.write(f'  TOTAL: {rainfall_today + weather_today + tide_today} records')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✓ FloodRecord data will NOT be affected'))
        self.stdout.write('')
        
        if rainfall_count + weather_count + tide_count == 0:
            self.stdout.write(self.style.SUCCESS('No dummy data found to delete!'))
            return
        
        # Confirm deletion
        if not options['confirm']:
            self.stdout.write(self.style.WARNING('⚠️  This action cannot be undone!'))
            confirm = input('Type "DELETE" to proceed: ')
            if confirm != 'DELETE':
                self.stdout.write(self.style.ERROR('Deletion cancelled.'))
                return
        
        # Perform deletion
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Deleting records...'))
        
        try:
            rainfall_deleted = RainfallData.objects.filter(timestamp__lt=today_start).delete()
            self.stdout.write(self.style.SUCCESS(f'✓ Deleted {rainfall_deleted[0]} RainfallData records'))
            
            weather_deleted = WeatherData.objects.filter(timestamp__lt=today_start).delete()
            self.stdout.write(self.style.SUCCESS(f'✓ Deleted {weather_deleted[0]} WeatherData records'))
            
            tide_deleted = TideLevelData.objects.filter(timestamp__lt=today_start).delete()
            self.stdout.write(self.style.SUCCESS(f'✓ Deleted {tide_deleted[0]} TideLevelData records'))
            
            total_deleted = rainfall_deleted[0] + weather_deleted[0] + tide_deleted[0]
            
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS(f'✓ Successfully deleted {total_deleted} dummy records!'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error during deletion: {str(e)}'))
            raise
