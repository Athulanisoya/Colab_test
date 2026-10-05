"""Compatibility registry: table definitions live in backend.models.

Importing this module registers every domain mapping with the shared metadata.
"""
from backend.database.connection import Base
from backend.models import (
    utcnow, User, RefreshToken, PasswordReset, Notification, AuditLog, ChatMessage, Team, Incident, ReportAnalysis, StatusHistory, Assignment, InvestigationReport, Alert, News, SafetyTip, Shelter, Inventory, ReliefRequest, Distribution, Campaign, Pledge,
    RoleRecord, UserRole, TeamMember, ChatSession, RecoveryMail, DisasterType, SeverityPrediction, AlertMatch, ShelterUpdateRecord, ShelterOccupancy, Donation, PaymentTransaction
)
