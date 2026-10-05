"""Register all domain mappings with the shared SQLAlchemy Base."""
from .user import utcnow, User, RefreshToken, PasswordReset, Notification, AuditLog, ChatMessage, RoleRecord, UserRole, ChatSession, RecoveryMail
from .team import Team, TeamMember
from .incident import Incident, ReportAnalysis, StatusHistory, Assignment, InvestigationReport, DisasterType, SeverityPrediction, AlertMatch
from .alert import Alert, News, SafetyTip
from .shelter import Shelter, ShelterUpdateRecord, ShelterOccupancy
from .inventory import Inventory, ReliefRequest, Distribution
from .donation import Campaign, Pledge, Donation, PaymentTransaction
