from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list[UserRole]] = relationship(back_populates="user", cascade="all, delete-orphan")
    profile: Mapped[UserProfile | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    personal_info: Mapped[UserPersonalInfo | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list[UserRole]] = relationship(back_populates="role", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="users")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(32))
    diet_type: Mapped[str | None] = mapped_column(String(64))
    activity_level: Mapped[str | None] = mapped_column(String(64))
    age_years: Mapped[int | None] = mapped_column(Integer)
    weight_value: Mapped[float | None] = mapped_column(Float)
    weight_unit: Mapped[str | None] = mapped_column(String(24))
    weight_kg: Mapped[float | None] = mapped_column(Float)
    height_value: Mapped[float | None] = mapped_column(Float)
    height_unit: Mapped[str | None] = mapped_column(String(24))
    height_cm: Mapped[float | None] = mapped_column(Float)
    health_goals: Mapped[dict] = mapped_column(JSONB, default=dict)
    allergies: Mapped[dict] = mapped_column(JSONB, default=dict)
    medical_warnings: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")


class UserPersonalInfo(Base):
    __tablename__ = "user_personal_info"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40))
    country: Mapped[str | None] = mapped_column(String(80))
    city: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str | None] = mapped_column(String(120))
    address_line: Mapped[str | None] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    document_type: Mapped[str | None] = mapped_column(String(40))
    document_number: Mapped[str | None] = mapped_column(String(80))
    preferences_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="personal_info")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    requested_ip: Mapped[str | None] = mapped_column(String(80))
    user_agent: Mapped[str | None] = mapped_column(Text)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    replaced_by_token_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    requested_ip: Mapped[str | None] = mapped_column(String(80))
    user_agent: Mapped[str | None] = mapped_column(Text)


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    base_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    products: Mapped[list[CommercialProduct]] = relationship(back_populates="pharmacy")


class Component(Base):
    __tablename__ = "components"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    component_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    canonical_name: Mapped[str] = mapped_column(String(320), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    safety_notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    products: Mapped[list[CommercialProductComponent]] = relationship(back_populates="component")


class CommercialProduct(Base):
    __tablename__ = "commercial_products"
    __table_args__ = (
        UniqueConstraint("pharmacy_id", "sku", name="uq_commercial_products_pharmacy_sku"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    pharmacy_id: Mapped[UUID] = mapped_column(ForeignKey("pharmacies.id", ondelete="RESTRICT"), index=True)
    sku: Mapped[str | None] = mapped_column(String(160), index=True)
    commercial_name: Mapped[str] = mapped_column(Text)
    formal_name: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(180), index=True)
    url: Mapped[str] = mapped_column(Text)
    registro_sanitario: Mapped[str | None] = mapped_column(String(80), index=True)
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="PEN")
    availability: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    stock: Mapped[int | None] = mapped_column(Integer)
    source_strategy: Mapped[str | None] = mapped_column(String(120))
    component_traceable: Mapped[str | None] = mapped_column(String(80), index=True)
    commercial_status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    raw_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    pharmacy: Mapped[Pharmacy] = relationship(back_populates="products")
    components: Mapped[list[CommercialProductComponent]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class CommercialProductComponent(Base):
    __tablename__ = "commercial_product_components"
    __table_args__ = (
        UniqueConstraint("product_id", "component_id", "ingredient", name="uq_product_component_ingredient"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_products.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[UUID] = mapped_column(ForeignKey("components.id", ondelete="RESTRICT"), index=True)
    ingredient: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[str | None] = mapped_column(String(80))
    unit: Mapped[str | None] = mapped_column(String(40))
    amount_mg: Mapped[float | None] = mapped_column(Float)
    match_score: Mapped[float | None] = mapped_column(Float)
    match_method: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(80), default="catalog_import")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped[CommercialProduct] = relationship(back_populates="components")
    component: Mapped[Component] = relationship(back_populates="products")


class IngredientSafetyRule(Base):
    __tablename__ = "ingredient_safety_rules"
    __table_args__ = (UniqueConstraint("name", name="uq_ingredient_safety_rules_name"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), index=True)
    ingredient_pattern: Mapped[str] = mapped_column(Text)
    restriction_code: Mapped[str | None] = mapped_column(String(80), index=True)
    safety_condition_code: Mapped[str | None] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(40), default="warn", index=True)
    severity: Mapped[str] = mapped_column(String(40), default="medium", index=True)
    message: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source: Mapped[str] = mapped_column(String(120), default="system_seed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StagingScrapedProduct(Base):
    __tablename__ = "staging_scraped_products"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    import_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("catalog_import_runs.id", ondelete="SET NULL"), index=True)
    pharmacy: Mapped[str] = mapped_column(String(160), index=True)
    sku: Mapped[str | None] = mapped_column(String(160), index=True)
    url: Mapped[str | None] = mapped_column(Text)
    commercial_name: Mapped[str | None] = mapped_column(Text)
    registro_sanitario: Mapped[str | None] = mapped_column(String(80), index=True)
    price: Mapped[float | None] = mapped_column(Float)
    availability: Mapped[str | None] = mapped_column(String(40), index=True)
    validation_status: Mapped[str] = mapped_column(String(80), default="pending", index=True)
    raw_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CatalogImportRun(Base):
    __tablename__ = "catalog_import_runs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(160), default="approved_catalog_csv")
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_scraped: Mapped[int] = mapped_column(Integer, default=0)
    total_accepted: Mapped[int] = mapped_column(Integer, default=0)
    total_rejected: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)


class CatalogJob(Base):
    __tablename__ = "catalog_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    mode: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    pid: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returncode: Mapped[int | None] = mapped_column(Integer)
    log_path: Mapped[str | None] = mapped_column(Text)
    requested_params_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    diff_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProductPriceSnapshot(Base):
    __tablename__ = "product_price_snapshots"
    __table_args__ = (
        Index("ix_product_price_snapshots_product_seen", "product_id", "seen_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("commercial_products.id", ondelete="SET NULL"), index=True)
    catalog_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("catalog_jobs.id", ondelete="SET NULL"), index=True)
    pharmacy: Mapped[str] = mapped_column(String(160), index=True)
    sku: Mapped[str | None] = mapped_column(String(160), index=True)
    url: Mapped[str | None] = mapped_column(Text)
    commercial_name: Mapped[str | None] = mapped_column(Text)
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    availability: Mapped[str | None] = mapped_column(String(40), index=True)
    stock: Mapped[int | None] = mapped_column(Integer)
    registro_sanitario: Mapped[str | None] = mapped_column(String(80), index=True)
    raw_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CatalogImportError(Base):
    __tablename__ = "catalog_import_errors"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    import_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("catalog_import_runs.id", ondelete="CASCADE"), index=True)
    pharmacy: Mapped[str | None] = mapped_column(String(160))
    sku: Mapped[str | None] = mapped_column(String(160))
    url: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    raw_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecommendationSession(Base):
    __tablename__ = "recommendation_sessions"
    __table_args__ = (
        Index("ix_recommendation_sessions_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    anonymous_session_id: Mapped[str | None] = mapped_column(String(120), index=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    input_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    conditions_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    profile_warnings_json: Mapped[list] = mapped_column(JSONB, default=list)
    model_versions_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    items: Mapped[list[RecommendationItem]] = relationship(back_populates="session", cascade="all, delete-orphan")
    packs: Mapped[list[RecommendedPack]] = relationship(back_populates="session", cascade="all, delete-orphan")


class LabReport(Base):
    __tablename__ = "lab_reports"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="manual", index=True)
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_mime_type: Mapped[str | None] = mapped_column(String(120))
    raw_text: Mapped[str | None] = mapped_column(Text)
    parsed_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    analysis_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    consent_health_data: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="processed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    biomarkers: Mapped[list[LabBiomarkerResult]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
    )


class LabBiomarkerResult(Base):
    __tablename__ = "lab_biomarker_results"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    lab_report_id: Mapped[UUID] = mapped_column(ForeignKey("lab_reports.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(180))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40))
    reference_low: Mapped[float | None] = mapped_column(Float)
    reference_high: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report: Mapped[LabReport] = relationship(back_populates="biomarkers")


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    recommendation_session_id: Mapped[UUID] = mapped_column(ForeignKey("recommendation_sessions.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[UUID | None] = mapped_column(ForeignKey("components.id", ondelete="SET NULL"), index=True)
    external_component_id: Mapped[str | None] = mapped_column(String(120), index=True)
    component_name: Mapped[str | None] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    score_model: Mapped[float | None] = mapped_column(Float)
    recommendation_type: Mapped[str | None] = mapped_column(String(120), index=True)
    condition_code: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[RecommendationSession] = relationship(back_populates="items")


class RecommendedPack(Base):
    __tablename__ = "recommended_packs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    recommendation_session_id: Mapped[UUID] = mapped_column(ForeignKey("recommendation_sessions.id", ondelete="CASCADE"), index=True)
    pack_key: Mapped[str] = mapped_column(String(160), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    score_final: Mapped[float | None] = mapped_column(Float)
    score_gnn: Mapped[float | None] = mapped_column(Float)
    score_coverage: Mapped[float | None] = mapped_column(Float)
    score_feedback: Mapped[float | None] = mapped_column(Float)
    score_reviews: Mapped[float | None] = mapped_column(Float)
    score_exposure: Mapped[float | None] = mapped_column(Float)
    score_products: Mapped[float | None] = mapped_column(Float)
    score_diversity: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[RecommendationSession] = relationship(back_populates="packs")
    items: Mapped[list[RecommendedPackItem]] = relationship(back_populates="pack", cascade="all, delete-orphan")


class RecommendedPackItem(Base):
    __tablename__ = "recommended_pack_items"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    recommended_pack_id: Mapped[UUID] = mapped_column(ForeignKey("recommended_packs.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[UUID | None] = mapped_column(ForeignKey("components.id", ondelete="SET NULL"), index=True)
    external_component_id: Mapped[str | None] = mapped_column(String(120), index=True)
    component_name: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("commercial_products.id", ondelete="SET NULL"), index=True)
    price_at_recommendation: Mapped[float | None] = mapped_column(Float)
    availability_at_recommendation: Mapped[str | None] = mapped_column(String(40))
    product_score: Mapped[float | None] = mapped_column(Float)
    match_score: Mapped[float | None] = mapped_column(Float)
    review_score: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)
    avg_rating: Mapped[float | None] = mapped_column(Float)
    bayesian_review_score: Mapped[float | None] = mapped_column(Float)
    price_score: Mapped[float | None] = mapped_column(Float)
    stock_score: Mapped[float | None] = mapped_column(Float)
    traceability_score: Mapped[float | None] = mapped_column(Float)
    pharmacy_diversity_score: Mapped[float | None] = mapped_column(Float)
    freshness_score: Mapped[float | None] = mapped_column(Float)
    selection_metrics_json: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pack: Mapped[RecommendedPack] = relationship(back_populates="items")
    product: Mapped[CommercialProduct | None] = relationship()


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    recommendation_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("recommendation_sessions.id", ondelete="SET NULL"), index=True)
    recommended_pack_id: Mapped[UUID | None] = mapped_column(ForeignKey("recommended_packs.id", ondelete="SET NULL"), index=True)
    pack_key: Mapped[str | None] = mapped_column(String(160), index=True)
    component_ids_json: Mapped[list] = mapped_column(JSONB, default=list)
    selected_product_ids_json: Mapped[list] = mapped_column(JSONB, default=list)
    chosen_product_id: Mapped[UUID | None] = mapped_column(ForeignKey("commercial_products.id", ondelete="SET NULL"), index=True)
    product_context_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    conditions_context_json: Mapped[list] = mapped_column(JSONB, default=list)
    # pack_key|COND_A+COND_B+COND_C (ver app/domains/feedback/contexto.py). Nullable: historico previo.
    context_key: Mapped[str | None] = mapped_column(String(400), index=True)
    # Outcomes declarados (purchased, still_taking_30d, perceived_benefit) + reward calculada.
    outcome_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    rating: Mapped[int | None] = mapped_column(Integer)
    was_relevant: Mapped[bool | None] = mapped_column(Boolean)
    would_follow: Mapped[bool | None] = mapped_column(Boolean)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    chosen_product: Mapped[CommercialProduct | None] = relationship()
    item_ratings: Mapped[list[RecommendationItemFeedback]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan", passive_deletes=True
    )


class RecommendationItemFeedback(Base):
    """Calificacion de 1 a 5 estrellas de un suplemento recomendado (docs/propuesta_recomendacion_por_suplemento.md).

    Se agrega por `context_key = component_id|condicion`: un suplemento puede servir para una condicion y no para
    otra. La condicion la pone el servidor desde `recommendation_items`, no el cliente. Cuelga del feedback general:
    un nuevo envio del mismo feedback reemplaza sus calificaciones en vez de sumar votos.
    """

    __tablename__ = "recommendation_item_feedback"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    recommendation_feedback_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendation_feedback.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    recommendation_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("recommendation_sessions.id", ondelete="SET NULL"), index=True)
    component_id: Mapped[str] = mapped_column(String(120), index=True)
    condition_code: Mapped[str | None] = mapped_column(String(120), index=True)
    context_key: Mapped[str] = mapped_column(String(260), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    # purchased, still_taking_30d + reward calculada (misma formula que el feedback general).
    outcome_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    feedback: Mapped[RecommendationFeedback] = relationship(back_populates="item_ratings")


RECOMMENDATION_EVENT_TYPES: tuple[str, ...] = (
    "impression",
    "click",
    "product_click",
    "purchase_intent",
    "dismiss",
    "still_taking_30d",
    "stopped",
)


class RecommendationEvent(Base):
    """Interacciones con recomendaciones mostradas (impresion, click, compra, retencion a 30 dias).

    Base de datos de interacciones para el futuro recomendador (bandit contextual / learning-to-rank).
    `position` guarda el rank mostrado para poder corregir el sesgo de posicion; `context_key` agrupa
    por pack + condiciones principales. Ver docs/recommender_events.md.
    """

    __tablename__ = "recommendation_events"
    __table_args__ = (
        Index("ix_recommendation_events_session_type", "recommendation_session_id", "event_type"),
        Index("ix_recommendation_events_context_type", "context_key", "event_type"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    recommendation_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recommendation_sessions.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    anonymous_session_id: Mapped[str | None] = mapped_column(String(120), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    pack_key: Mapped[str | None] = mapped_column(String(160), index=True)
    component_id: Mapped[str | None] = mapped_column(String(120))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("commercial_products.id", ondelete="SET NULL"), index=True)
    position: Mapped[int | None] = mapped_column(Integer)
    conditions_context_json: Mapped[list] = mapped_column(JSONB, default=list)
    context_key: Mapped[str | None] = mapped_column(String(400), index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SupplementReview(Base):
    __tablename__ = "supplement_reviews"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_products.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[UUID | None] = mapped_column(ForeignKey("components.id", ondelete="SET NULL"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    effectiveness_score: Mapped[int | None] = mapped_column(Integer)
    side_effects_score: Mapped[int | None] = mapped_column(Integer)
    price_value_score: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="published", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    product: Mapped[CommercialProduct] = relationship()
    component: Mapped[Component | None] = relationship()


class PackReview(Base):
    __tablename__ = "pack_reviews"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    recommended_pack_id: Mapped[UUID] = mapped_column(ForeignKey("recommended_packs.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    followed_recommendation: Mapped[bool | None] = mapped_column(Boolean)
    felt_improvement: Mapped[bool | None] = mapped_column(Boolean)
    side_effects: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CatalogOverride(Base):
    __tablename__ = "catalog_overrides"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_products.id", ondelete="CASCADE"), index=True)
    status: Mapped[str | None] = mapped_column(String(40))
    preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    admin_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    admin_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action_type: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(120), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(160), index=True)
    before_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    after_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CatalogRsReview(Base):
    """Cola de revisión humana de registros sanitarios (RS) del catálogo.

    Una fila por producto comercial (pharmacy + sku) cuyo RS fue inferido por
    nombre contra DIGEMID (`sample_reason="inferred"`) o que entró en la muestra
    aleatoria de control (`sample_reason="random_sample"`). Ver docs/catalog_rs_review.md.
    """

    __tablename__ = "catalog_rs_reviews"
    __table_args__ = (
        UniqueConstraint("pharmacy", "sku", "registro_sanitario_key", name="uq_catalog_rs_reviews_pharmacy_sku_rs"),
        Index("ix_catalog_rs_reviews_status_sample", "status", "sample_reason"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    pharmacy: Mapped[str] = mapped_column(String(160), index=True)
    sku: Mapped[str] = mapped_column(String(160), index=True)
    url: Mapped[str | None] = mapped_column(Text)
    commercial_name: Mapped[str | None] = mapped_column(Text)
    registro_sanitario_key: Mapped[str] = mapped_column(String(80), index=True)
    digemid_producto: Mapped[str | None] = mapped_column(Text)
    digemid_composicion: Mapped[str | None] = mapped_column(Text)
    registro_sanitario_source: Mapped[str | None] = mapped_column(String(80), index=True)
    match_reason: Mapped[str | None] = mapped_column(Text)
    sample_reason: Mapped[str] = mapped_column(String(40), index=True)  # inferred | random_sample
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)  # pending|approved|rejected|needs_info
    reviewer_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SurveyStepEvent(Base):
    """Embudo de la encuesta: que pasos se ven, se completan y donde se abandona (contrato 2026-10-24.1).

    No cuelga de una recomendacion: quien abandona nunca llega a tenerla. `survey_session_id` lo genera la app
    al iniciar cada encuesta. No guarda respuestas, solo la clave del paso.
    """

    __tablename__ = "survey_step_events"
    __table_args__ = (Index("ix_survey_step_events_session_step", "survey_session_id", "step_key"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    survey_session_id: Mapped[str] = mapped_column(String(80), index=True)
    step_key: Mapped[str] = mapped_column(String(80), index=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)  # view | complete | submit
    position: Mapped[int | None] = mapped_column(Integer)
    visible_steps: Mapped[int | None] = mapped_column(Integer)
    contract_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

