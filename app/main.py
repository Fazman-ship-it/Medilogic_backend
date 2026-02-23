from fastapi import FastAPI
from app.routes import trip
from app.routes import trip, user
from app.database import engine, Base
from app import models, config
from app.routes import access, user
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from app.dependencies import get_current_user, require_role
from app.config import settings
from app.routes import trip_analytics,trip
from app.routes import trip_analytics2
from app.scheduler import scheduler
from fastapi.staticfiles import StaticFiles
from app.routes import dashboard
from app.routes import pod
import os
from app.routes import admin_dashboard
from app.routes import client_trip_booking
from app.routes import invoices
from app.routes import trip_assignment
from app.routes import recommendation
from app.routes import scheduler_optimizer
from app.routes import driver
from app.routes import system_configuration
from app.routes import support
from app.routes import ai_assistant
from app.routes import public_signup
from app.routes import super_admin
from app.routes import legal
from app.routes import regulator_dashboard
from app.routes import enquiries
from app.routes import incidents
from app.routes import compliance
from app.routes import profile
from app.routes import activity_logs
from app.routes import driver_availability
from app.routes import shifts
from app.scheduler import start_scheduler
from app.routes import chain_of_custody
from app.routes import driver_location
from app.routes import websockets
from app.routes import location_analytics
from app.routes import admin_users
from app.routes import testimonials
from app.routes import applications
from app.routes import confirm_receipt
from app.routes import app_notifications
from app.routes import com
from app.routes import document_upload
from app.routes import driver_credentials
from app.routes import international_application
from app.routes import appliciant_analytics
from app.routes import subscriptions
from app.routes import stripe_webhook
from app.routes import medilogic_driver
from app.routes import daily_notification
from app.routes import chatbot
from app.routes import hookstripe
# app/main.py

app = FastAPI(
    title="Medilogic API",
    description="API for managing medical waste trips ,deliveries and compliances",
    version="1.0.0",
    docs_url="/docs",             # Swagger UI
    redoc_url="/redoc",           # ReDoc UI
    openapi_url="/openapi.json"   # OpenAPI spec
)
# ✅ CORS middleware to allow Swagger to send token in headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://medilogicglobal.vercel.app",  # In production, set this to your frontend domain
        "https://medilogic.vercel.app",
        # ✅ ADD THESE FOR LOCAL DEVELOPMENT
        "http://localhost:3000",   # React / Next.js
        "http://127.0.0.1:3000",
        "http://localhost:5173",   # Vite
        "http://127.0.0.1:5173",
    ],           
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trip.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to Medilogic API"}

# Include user routes
app.include_router(trip_analytics.router, prefix="/analytics", tags=["Trip Analytics"])  # Trip analytics routes
app.include_router(trip.router, prefix="/trips", tags=["trips"])  # Trip routes 
app.include_router(user.router, prefix="/users", tags=["users"])
app.include_router(access.router, prefix="/access", tags=["Access Control"])
app.include_router(trip_analytics2.router, prefix="/export", tags=["Trip Export"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboards"])
app.include_router(pod.router,prefix="/pods", tags=["PODs"])
app.include_router(admin_dashboard.router, prefix="/admin-dashboard", tags=["Admin Dashboard"])
app.include_router(client_trip_booking.router)
app.include_router(invoices.router)
app.include_router(trip_assignment.router)
app.include_router(recommendation.router)
app.include_router(scheduler_optimizer.router)
app.include_router(driver.router)
app.include_router(system_configuration.router)
app.include_router(support.router)
app.include_router(ai_assistant.router)
app.include_router(public_signup.router)
app.include_router(super_admin.router)
app.include_router(legal.router)
app.include_router(regulator_dashboard.router)
app.include_router(enquiries.router)
app.include_router(incidents.router)
app.include_router(compliance.router)
app.include_router(profile.router)
app.include_router(activity_logs.router)
app.include_router(driver_availability.router)
app.include_router(shifts.router)
app.include_router(chain_of_custody.router)
app.include_router(driver_location.router)
app.include_router(websockets.router)
app.include_router(location_analytics.router)
app.include_router(admin_users.router)
app.include_router(testimonials.router)
app.include_router(applications.router)
app.include_router(confirm_receipt.router)
app.include_router(app_notifications.router)
app.include_router(com.router)
app.include_router(document_upload.router)
app.include_router(driver_credentials.router)
app.include_router(international_application.router)
app.include_router(appliciant_analytics.router)
app.include_router(subscriptions.router)
app.include_router(stripe_webhook.router)
app.include_router(medilogic_driver.router)
app.include_router(daily_notification.router)
app.include_router(chatbot.router)
app.include_router(hookstripe.router)
# Create database tables
# ✅ Swagger UI JWT Bearer token support
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Medilogic API",
        version="1.0.0",
        description="API for medical and clinical waste logistics",
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    for path in openapi_schema["paths"].values():
        for method in path.values():
            method.setdefault("security", []).append({"BearerAuth": []})

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Inside the block where your FastAPI app is initialized (after app creation)
start_scheduler()

