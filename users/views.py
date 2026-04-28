from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from .forms import CustomUserCreationForm, AdminRegistrationForm, ProfileEditForm
from .models import CustomUser, UserLog, LoginAttempt
from .validators import PasswordStrengthValidator
from monitoring.views import get_flood_risk_level, get_tide_risk_level, get_combined_risk_level

def register(request):
    """
    Handle user registration with auto-generated staff ID.
    
    Staff ID Format: YEAR + sequential 4-digit number (e.g., 20250001)
    The user account is created as inactive pending admin approval.
    
    Uses select_for_update() inside transaction.atomic() to prevent race conditions
    when two users register simultaneously and could receive the same Staff ID.
    
    Args:
        request: HttpRequest object
        
    Returns:
        HttpResponse: Rendered registration form or redirect to login
    """
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.is_approved = False
            
            from datetime import datetime
            current_year = datetime.now().year
            
            with transaction.atomic():
                # Lock existing staff IDs for this year to prevent concurrent duplicates
                existing_ids = list(
                    CustomUser.objects.filter(
                        staff_id__startswith=str(current_year)
                    ).select_for_update().order_by('-staff_id')
                    .values_list('staff_id', flat=True)
                )
                
                if existing_ids:
                    try:
                        last_number = int(existing_ids[0][-4:])
                        new_number = last_number + 1
                    except (ValueError, TypeError):
                        new_number = 1
                else:
                    new_number = 1
                
                # Format: YEAR + 4-digit sequential number (e.g., 20260001)
                user.staff_id = f"{current_year}{new_number:04d}"
                user.save()
            
            messages.success(request, f'Account created successfully! Your Staff ID is {user.staff_id}. Please wait for admin approval.')
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'users/register.html', {'form': form})

@login_required
@staff_member_required
def approve_users(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        user = get_object_or_404(CustomUser, id=user_id)
        
        if action == 'approve':
            if not user.is_superuser:  # Prevent modifying superuser status
                user.is_active = True
                user.is_approved = True
                user.save()
                UserLog.objects.create(
                    user=request.user,
                    action=f"Approved user {user.username}"
                )
                messages.success(request, f"User {user.username} has been approved.")
        
        elif action == 'delete':
            if user.is_superuser:
                messages.error(request, "Cannot delete superuser accounts.")
            else:
                username = user.username
                user.delete()
                UserLog.objects.create(
                    user=request.user,
                    action=f"Deleted user {username}"
                )
                messages.success(request, f"User {username} has been deleted.")
        
        return redirect('approve_users')
    
    # Get all users except superusers for the list
    users = CustomUser.objects.filter(is_superuser=False).order_by('-date_joined')
    return render(request, 'users/approve_users.html', {'users': users})

def user_login(request):
    if request.user.is_authenticated:  # Check if already logged in—redirect to dashboard
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        ip_address = request.META.get('REMOTE_ADDR', '0.0.0.0')
        
        # Check for too many failed attempts
        failed_attempts = LoginAttempt.get_recent_failures(username, ip_address)
        if failed_attempts >= 5:  # Limit to 5 attempts per 30 minutes
            messages.error(request, "Too many failed login attempts. Please try again later.")
            return render(request, 'users/login.html', {'error': 'Too many failed attempts'})
        
        user = authenticate(request, username=username, password=password)
        login_successful = False
        
        if user is not None and user.is_active and user.is_approved:
            login(request, user)
            UserLog.objects.create(user=user, action="Logged in")
            login_successful = True
            messages.success(request, f"Welcome back, {user.username}!")
            
            # Clear failed attempts on successful login
            LoginAttempt.objects.filter(username=username, ip_address=ip_address).delete()
            return redirect('home')
        else:
            messages.error(request, "Invalid login credentials or account not approved.")
        
        # Log the attempt
        LoginAttempt.objects.create(
            username=username,
            ip_address=ip_address,
            success=login_successful
        )
        
        return render(request, 'users/login.html', {
            'admin_exists': CustomUser.objects.filter(is_superuser=True).exists()
        })
    return render(request, 'users/login.html', {
        'admin_exists': CustomUser.objects.filter(is_superuser=True).exists()
    })

def user_logout(request):
    if request.user.is_authenticated:
        UserLog.objects.create(user=request.user, action="Logged out")
        messages.success(request, "You have been successfully logged out. See you next time!")
    logout(request)
    return redirect('login')

def admin_register(request):
    """
    Handle admin registration with auto-generated staff ID.
    
    Only allows registration if no admin exists yet.
    Admin accounts are automatically approved and activated.
    
    Args:
        request: HttpRequest object
        
    Returns:
        HttpResponse: Rendered registration form or redirect
    """
    if CustomUser.objects.filter(is_superuser=True).exists():
        messages.error(request, "Admin registration is disabled. An admin account already exists.")
        return redirect('login')
        
    if request.method == 'POST':
        form = AdminRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                
                from datetime import datetime
                current_year = datetime.now().year
                
                # Lock existing IDs for this year to prevent concurrent duplicate generation
                existing_ids = list(
                    CustomUser.objects.filter(
                        staff_id__startswith=str(current_year)
                    ).select_for_update().order_by('-staff_id')
                    .values_list('staff_id', flat=True)
                )
                
                if existing_ids:
                    try:
                        last_number = int(existing_ids[0][-4:])
                        new_number = last_number + 1
                    except (ValueError, TypeError):
                        new_number = 1
                else:
                    new_number = 1
                
                # Format: YEAR + 4-digit sequential number (e.g., 20260001)
                user.staff_id = f"{current_year}{new_number:04d}"
                
                # Set admin privileges
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.is_approved = True
                
                user.save()
                
                UserLog.objects.create(
                    user=user,
                    action=f"Created admin account with Staff ID: {user.staff_id}"
                )
                messages.success(request, f"Admin account created successfully! Your Staff ID is {user.staff_id}. You can now log in.")
                return redirect('login')
    else:
        form = AdminRegistrationForm()
    
    return render(request, 'users/admin_register.html', {'form': form})
@login_required
def home(request):
    context = {
        'pending_approvals': CustomUser.objects.filter(is_active=False, is_approved=False).count(),
        'recent_logs': UserLog.objects.all().order_by('-timestamp')[:5],
        'total_users': CustomUser.objects.filter(is_active=True).count(),
        'user_logs': UserLog.objects.filter(user=request.user).order_by('-timestamp')[:5]
    }

    # Admin summary cards context
    if request.user.is_staff:
        # Total activities: count of all UserLog, FloodRecordActivity, AssessmentRecord, ReportRecord, CertificateRecord
        from maps.models import FloodRecordActivity, AssessmentRecord, ReportRecord, CertificateRecord
        total_activities = (
            UserLog.objects.count() +
            FloodRecordActivity.objects.count() +
            AssessmentRecord.objects.count() +
            ReportRecord.objects.count() +
            CertificateRecord.objects.count()
        )
        # Most active users: top 5 users with most UserLog entries.
        # Uses 2 queries (aggregation + bulk fetch) instead of 1+N to avoid N+1 query problem.
        from django.db.models import Count
        activity_qs = (
            UserLog.objects
            .values('user')
            .annotate(activity_count=Count('id'))
            .order_by('-activity_count')[:5]
        )
        ordered_user_ids = [row['user'] for row in activity_qs]
        activity_count_map = {row['user']: row['activity_count'] for row in activity_qs}
        user_map = {u.id: u for u in CustomUser.objects.filter(id__in=ordered_user_ids)}
        most_active_users = []
        for uid in ordered_user_ids:
            user_obj = user_map.get(uid)
            if not user_obj:
                continue
            user_info = type('MostActiveUser', (), {})()
            user_info.username = user_obj.username
            user_info.activity_count = activity_count_map[uid]
            user_info.profile_image = user_obj.profile_image
            user_info.full_name = user_obj.get_full_name()
            most_active_users.append(user_info)

        # Recent activity highlights: last 5 from all activity models, sorted by timestamp/date
        recent_activity_highlights = []
        # UserLog
        for log in UserLog.objects.all().order_by('-timestamp')[:5]:
            log.type = 'UserLog'
            recent_activity_highlights.append(log)
        # FloodRecordActivity
        for flood in FloodRecordActivity.objects.all().order_by('-timestamp')[:5]:
            flood.type = 'FloodRecordActivity'
            flood.description = f"{flood.get_action_display()} flood record for {flood.event_type} by {flood.user.username}"
            flood.date = flood.timestamp
            recent_activity_highlights.append(flood)
        # AssessmentRecord
        for assess in AssessmentRecord.objects.all().order_by('-timestamp')[:5]:
            assess.type = 'AssessmentRecord'
            assess.summary = f"Assessment for {assess.barangay} by {assess.user.username}"
            assess.date = assess.timestamp
            recent_activity_highlights.append(assess)
        # ReportRecord
        for report in ReportRecord.objects.all().order_by('-timestamp')[:5]:
            report.type = 'ReportRecord'
            report.summary = f"Report for {report.barangay} by {report.user.username}"
            report.date = report.timestamp
            recent_activity_highlights.append(report)
        # CertificateRecord
        for cert in CertificateRecord.objects.all().order_by('-timestamp')[:5]:
            cert.type = 'CertificateRecord'
            cert.summary = f"Certificate for {cert.establishment_name} by {cert.user.username}"
            cert.date = cert.timestamp
            recent_activity_highlights.append(cert)
        # Sort all by date/timestamp descending
        recent_activity_highlights.sort(key=lambda x: getattr(x, 'timestamp', getattr(x, 'date', None)), reverse=True)
        context['total_activities'] = total_activities
        context['most_active_users'] = most_active_users
        context['recent_activity_highlights'] = recent_activity_highlights[:5]
    
    # Get latest monitoring data
    from monitoring.models import RainfallData, WeatherData, TideLevelData, FloodRecord
    from maps.models import Barangay, FloodSusceptibility
    from django.contrib.gis.measure import D
    from django.db.models import Q
    
    
    rainfall_data = RainfallData.objects.filter(timestamp__isnull=False).first()
    weather_data = WeatherData.objects.filter(timestamp__isnull=False).first()
    tide_data = TideLevelData.objects.filter(timestamp__isnull=False).first()
    recent_floods = FloodRecord.objects.all().order_by('-date')[:3]
    
    # Calculate highest risk barangay based on flood susceptibility data.
    # Uses at most 4 queries (one per risk level, stopping at first match) instead of
    # 1 query per barangay (N+1). Checks VHF → HF → MF → LF in priority order.
    highest_risk_barangay = None
    try:
        risk_level_map = {'VHF': 'Critical', 'HF': 'High', 'MF': 'Moderate', 'LF': 'Low'}
        for risk_code in ['VHF', 'HF', 'MF', 'LF']:
            zone = FloodSusceptibility.objects.filter(haz_code=risk_code).first()
            if not zone:
                continue
            barangay = Barangay.objects.filter(
                geometry__intersects=zone.geometry
            ).first()
            if barangay:
                highest_risk_barangay = type('HighestRiskBarangay', (), {})()
                highest_risk_barangay.name = barangay.name
                highest_risk_barangay.risk_level = risk_level_map[risk_code]
                break
    except Exception as e:
        print(f"Error calculating highest risk barangay: {e}")
        highest_risk_barangay = None
    
    if rainfall_data:
        rain_risk_level, rain_risk_color = get_flood_risk_level(rainfall_data.value_mm)
        context['rain_risk'] = {'level': rain_risk_level, 'color': rain_risk_color}
        
    if tide_data:
        tide_risk_level, tide_risk_color = get_tide_risk_level(tide_data.height_m)
        context['tide_risk'] = {'level': tide_risk_level, 'color': tide_risk_color}
    
    # Import BenchmarkSettings for alert thresholds
    from monitoring.models import BenchmarkSettings
        
    if rainfall_data and tide_data:
        combined_risk_level, combined_risk_color = get_combined_risk_level(rainfall_data.value_mm, tide_data.height_m)
        context['combined_risk'] = {'level': combined_risk_level, 'color': combined_risk_color}
        
        # Generate flood alerts based on risk level and conditions
        flood_alerts = []
        settings = BenchmarkSettings.get_settings()
        
        # HIGH RISK ALERTS
        if combined_risk_level == "High Risk":
            flood_alerts.append("🚨 HIGH FLOOD RISK: Both rainfall and tide levels are critically high!")
            flood_alerts.append(f"Current rainfall: {rainfall_data.value_mm}mm (High threshold: {settings.rainfall_high_threshold}mm)")
            flood_alerts.append(f"Current tide level: {tide_data.height_m}m (High threshold: {settings.tide_high_threshold}m)")
            flood_alerts.append("⚠️ IMMEDIATE ACTION: Monitor low-lying areas and prepare evacuation plans.")
        
        # MODERATE RISK ALERTS
        elif combined_risk_level == "Moderate Risk":
            flood_alerts.append("⚠️ MODERATE FLOOD RISK: Rainfall and tide levels are elevated.")
            flood_alerts.append(f"Current rainfall: {rainfall_data.value_mm}mm (Moderate threshold: {settings.rainfall_moderate_threshold}mm)")
            flood_alerts.append(f"Current tide level: {tide_data.height_m}m (Moderate threshold: {settings.tide_moderate_threshold}m)")
            flood_alerts.append("📋 ADVISORY: Stay alert and monitor conditions closely.")
        
        # LOW RISK - Still show informational alerts
        else:
            # Check individual thresholds for warnings
            if rainfall_data.value_mm >= settings.rainfall_moderate_threshold:
                flood_alerts.append(f"🌧️ Elevated Rainfall: Current {rainfall_data.value_mm}mm (above {settings.rainfall_moderate_threshold}mm threshold)")
            elif rainfall_data.value_mm >= settings.rainfall_moderate_threshold * 0.7:
                flood_alerts.append(f"☁️ Increasing Rainfall: Current {rainfall_data.value_mm}mm (approaching threshold)")
            
            if tide_data.height_m >= settings.tide_moderate_threshold:
                flood_alerts.append(f"🌊 High Tide Alert: Current {tide_data.height_m}m (above {settings.tide_moderate_threshold}m threshold)")
            elif tide_data.height_m >= settings.tide_moderate_threshold * 0.8:
                flood_alerts.append(f"🌊 Rising Tide: Current {tide_data.height_m}m (approaching threshold)")
            
            # If no specific warnings, show general status
            if not flood_alerts:
                flood_alerts.append(f"✅ Conditions Normal: Rainfall at {rainfall_data.value_mm}mm, Tide at {tide_data.height_m}m")
                flood_alerts.append("📊 Current conditions are within safe parameters.")
        
        # Add weather-based alerts
        if weather_data:
            if weather_data.wind_speed_kph > 50:
                flood_alerts.append(f"💨 Strong Winds: {weather_data.wind_speed_kph} km/h - Secure outdoor items")
            if weather_data.humidity_percent > 85:
                flood_alerts.append(f"💧 High Humidity: {weather_data.humidity_percent}% - Increased flood potential")
        
        context['flood_alerts'] = flood_alerts if flood_alerts else None
    
    context.update({
        'rainfall_data': rainfall_data,
        'weather_data': weather_data,
        'recent_floods': recent_floods,
        'highest_risk_barangay': highest_risk_barangay
    })
    
    return render(request, 'users/home.html', context)

@login_required
@staff_member_required
def user_logs(request):
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    logs_qs = UserLog.objects.select_related('user').order_by('-timestamp')
    paginator = Paginator(logs_qs, 25)  # 25 logs per page
    page_number = request.GET.get('page', 1)
    try:
        logs = paginator.page(page_number)
    except PageNotAnInteger:
        logs = paginator.page(1)
    except EmptyPage:
        logs = paginator.page(paginator.num_pages)
    return render(request, 'users/user_logs.html', {'logs': logs, 'paginator': paginator})

@login_required
def view_profile(request):
    """
    View and edit user profile.
    Handles profile information updates including profile image uploads.
    """
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save()
            UserLog.objects.create(user=user, action="Updated profile")
            messages.success(request, 'Profile updated successfully!')
            return redirect('view_profile')
        else:
            # Keep form errors and data for modal to reopen
            messages.error(request, 'Error updating profile. Please check the form and try again.')
    else:
        form = ProfileEditForm(instance=request.user)
    
    return render(request, 'users/profile.html', {'form': form})