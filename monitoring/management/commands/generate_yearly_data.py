from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from monitoring.models import RainfallData, WeatherData, TideLevelData
import random
import math


class Command(BaseCommand):
    help = 'Generate realistic hourly monitoring data for years 2024, 2025, and 2026 (partial)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing data before generating new data',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('=' * 70))
        self.stdout.write(self.style.WARNING('GENERATE YEARLY HOURLY DATA'))
        self.stdout.write(self.style.WARNING('=' * 70))
        self.stdout.write('')
        
        # Clear existing data if requested
        if options['clear_existing']:
            self.stdout.write(self.style.WARNING('Clearing existing data...'))
            RainfallData.objects.all().delete()
            WeatherData.objects.all().delete()
            TideLevelData.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('✓ Cleared all existing data'))
            self.stdout.write('')
        
        # Define date ranges
        date_ranges = [
            (2024, 1, 1, 2024, 12, 31, 'Year 2024'),  # Full year (leap year - 366 days)
            (2025, 1, 1, 2025, 12, 31, 'Year 2025'),  # Full year (365 days)
            (2026, 1, 1, 2026, 1, 13, 'Year 2026 (Jan 1-13)'),  # Partial year (13 days)
        ]
        
        total_records = 0
        
        for start_year, start_month, start_day, end_year, end_month, end_day, label in date_ranges:
            self.stdout.write(self.style.WARNING(f'\nGenerating data for {label}...'))
            
            start_date = datetime(start_year, start_month, start_day, 0, 0, 0)
            end_date = datetime(end_year, end_month, end_day, 23, 0, 0)
            
            current_date = start_date
            year_records = 0
            
            # Calculate total hours for progress tracking
            total_hours = int((end_date - start_date).total_seconds() / 3600) + 1
            
            while current_date <= end_date:
                # Make timezone-aware
                aware_timestamp = timezone.make_aware(current_date, timezone.get_current_timezone())
                
                # Generate realistic random values
                # Rainfall: 0-80mm with occasional spikes (realistic for tropical climate)
                rainfall = self._generate_rainfall()
                
                # Tide: 0.3-2.2m with semi-diurnal pattern (2 high tides per day)
                tide = self._generate_tide(current_date)
                
                # Weather: Temperature (24-34°C), Humidity (60-95%), Wind (5-40 kph)
                temperature = round(random.uniform(24.0, 34.0), 1)
                humidity = random.randint(60, 95)
                wind_speed = round(random.uniform(5.0, 40.0), 1)
                
                # Create records
                RainfallData.objects.create(
                    value_mm=rainfall,
                    timestamp=aware_timestamp,
                    station_name='Silay City'
                )
                
                WeatherData.objects.create(
                    temperature_c=temperature,
                    humidity_percent=humidity,
                    wind_speed_kph=wind_speed,
                    timestamp=aware_timestamp,
                    station_name='Silay City'
                )
                
                TideLevelData.objects.create(
                    height_m=tide,
                    timestamp=aware_timestamp,
                    station_name='Silay City'
                )
                
                year_records += 3  # 3 types of records per hour
                total_records += 3
                
                # Progress indicator (every 100 hours)
                if year_records % 300 == 0:
                    progress = int((year_records / 3) / total_hours * 100)
                    self.stdout.write(f'  Progress: {progress}% ({year_records // 3}/{total_hours} hours)', ending='\r')
                
                # Move to next hour
                current_date += timedelta(hours=1)
            
            self.stdout.write('')  # New line after progress
            self.stdout.write(self.style.SUCCESS(f'✓ Generated {year_records} records for {label}'))
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS(f'✓ Successfully generated {total_records} total records!'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')
        self.stdout.write('Summary:')
        self.stdout.write(f'  • 2024: 366 days × 24 hours = 8,784 hours')
        self.stdout.write(f'  • 2025: 365 days × 24 hours = 8,760 hours')
        self.stdout.write(f'  • 2026: 13 days × 24 hours = 312 hours')
        self.stdout.write(f'  • Total: {total_records // 3} hours × 3 record types = {total_records} records')

    def _generate_rainfall(self):
        """Generate realistic rainfall values (0-80mm, mostly low with occasional spikes)"""
        # 70% chance of low rainfall (0-10mm)
        if random.random() < 0.7:
            return round(random.uniform(0, 10), 1)
        # 20% chance of moderate rainfall (10-40mm)
        elif random.random() < 0.9:
            return round(random.uniform(10, 40), 1)
        # 10% chance of heavy rainfall (40-80mm)
        else:
            return round(random.uniform(40, 80), 1)
    
    def _generate_tide(self, current_date):
        """Generate realistic tide levels with semi-diurnal pattern (2 high/low tides per day)"""
        # Use sine wave to simulate tidal patterns
        # 2 cycles per day (semi-diurnal tides)
        hour = current_date.hour + (current_date.minute / 60.0)
        # Period is 12 hours (2 tides per day)
        tide_base = 1.25  # Average tide level
        tide_amplitude = 0.75  # Tide range (±0.75m)
        tide = tide_base + tide_amplitude * math.sin(2 * math.pi * hour / 12)
        
        # Add small random variation
        tide += random.uniform(-0.1, 0.1)
        
        # Ensure tide stays within realistic bounds (0.3-2.2m)
        tide = max(0.3, min(2.2, tide))
        
        return round(tide, 2)
