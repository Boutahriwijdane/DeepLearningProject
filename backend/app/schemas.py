from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class InvoiceFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    supplier: str | None = Field(None, max_length=255)
    invoice_number: str | None = Field(None, max_length=100)
    invoice_date: date | None = None
    currency: str = Field('MAD', pattern=r'^[A-Z]{3}$')
    subtotal: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    tax: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    total: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)

    @field_validator('supplier', 'invoice_number')
    @classmethod
    def blank_to_none(cls, value):
        return value or None

class MLResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['demo', 'real']
    model_version: str
    classification: Literal['invoice', 'receipt', 'other'] | None
    confidence: float | None = Field(None, ge=0, le=1)
    quality: Literal['acceptable', 'retake_required', 'unknown']
    warnings: list[str] = []
    ocr_text: str = ''
    fields: InvoiceFields = Field(default_factory=InvoiceFields)
