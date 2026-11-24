from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field, AliasChoices, field_validator

class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True, populate_by_name=True)

# Currency input: exact shillings with at most two decimal places.
MoneyIn = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]

Role = Literal["waiter", "cashier", "manager", "director", "store_manager", "carwash_manager", "kitchen"]
PaymentMethod = Literal["cash", "m-pesa"]

class LoginIn(BaseModel):
    username: str
    password: str
    role: Role | None = None
class RefreshIn(BaseModel): refresh_token: str
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    role: Role
    full_name: str | None = None
    department_id: int | None = None
class UserUpdate(BaseModel):
    department_id: int | None = None
    full_name: str | None = None
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

class MenuDetails(BaseModel):
    description: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=500)
    tax_rate: Literal[16] = 16

    @field_validator("image_url")
    @classmethod
    def valid_image(cls, value):
        from urllib.parse import urlparse
        import re
        if not value: return None
        parsed = urlparse(value)
        if (parsed.scheme in {"https", "http"} and parsed.netloc and not parsed.username and not parsed.password) or re.fullmatch(r"/api/menu-images/[a-f0-9]{32}", value):
            return value
        raise ValueError("Use an HTTP(S) image URL or upload a food photo")

class MenuImageUpload(BaseModel):
    data: str = Field(max_length=2800000)

class MenuCreate(MenuDetails):
    name: str = Field(min_length=1); price: MoneyIn = Field(gt=0); category_id: int; department_id: int; active: bool = True
class MenuUpdate(MenuDetails):
    name: str | None = Field(default=None, min_length=1); price: MoneyIn | None = Field(default=None, gt=0)
    category_id: int | None = None; department_id: int | None = None; active: bool | None = None
class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None
    is_active: bool = True
class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    is_active: bool = True
    printer_ip: str | None = None
    printer_port: int = Field(default=9100, ge=1, le=65535)

class OrderLineIn(BaseModel): menu_item_id: int; quantity: int = Field(gt=0, le=100)
class OrderCreate(BaseModel):
    table_id: int = Field(gt=0)
    items: list[OrderLineIn] = Field(min_length=1, max_length=100)
    customer: str | None = None
    notes: str | None = None
class OrderUpdate(BaseModel):
    status: Literal["pending", "printed", "ready", "payment_pending", "cleared", "completed"] = Field(validation_alias=AliasChoices("status", "new_status"))
class PaymentCreate(BaseModel):
    tendered_amount: MoneyIn | None = Field(default=None, ge=0)
    expected_version: int | None = Field(default=None, ge=1)
    method: PaymentMethod
    amount: MoneyIn = Field(gt=0)
    reference: str | None = Field(default=None, validation_alias=AliasChoices("reference", "reference_number"))
    notes: str | None = None

class IngredientCreate(BaseModel):
    name: str; unit: str; min_level: float = Field(ge=0); current_stock: float = Field(default=0, ge=0)
    description: str | None = None
    reorder_quantity: float = Field(default=0, ge=0)
    cost_per_unit: float = Field(default=0, ge=0)
class StockChange(BaseModel): ingredient_id: int; quantity: float = Field(ge=0); reason: str | None = None

class CarWashCreate(BaseModel):
    vehicle_plate: str = Field(min_length=3, max_length=20)
    payment_method: PaymentMethod; amount: MoneyIn = Field(gt=0); notes: str | None = None
    payment_status: Literal["pending", "completed"] = "completed"
    bay_id: int | None = None
    service_id: int | None = None
    vehicle_type: str | None = None
    mpesa_reference: str | None = None
    @field_validator("vehicle_plate")
    @classmethod
    def normalize_plate(cls, value: str): return " ".join(value.upper().split())

class PrinterConfig(BaseModel):
    department_id: int
    printer_ip: str
    printer_port: int = Field(default=9100, ge=1, le=65535)

class BayCreate(BaseModel):
    bay_number: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=80)
    is_active: bool = True

class WashServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    price: MoneyIn = Field(gt=0)
    duration_minutes: int = Field(default=30, gt=0)
    is_active: bool = True

class TableCreate(BaseModel):
    number: int = Field(gt=0, le=9999)
    is_active: bool = True

class TableUpdate(BaseModel):
    is_active: bool

class OrderAddition(BaseModel):
    expected_version: int = Field(ge=1)
    items: list[OrderLineIn] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)

class RemovalLine(BaseModel):
    order_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0)

class ChangeCreate(BaseModel):
    expected_version: int = Field(ge=1)
    kind: Literal["remove", "cancel"]
    items: list[RemovalLine] = Field(default_factory=list, max_length=100)
    reason: str = Field(min_length=3, max_length=1000)

class ChangeDecision(BaseModel):
    expected_version: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=1000)

