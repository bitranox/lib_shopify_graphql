"""Shopify API domain enumerations.

This module contains StrEnum types for Shopify API domain values:
    - ProductStatus, InventoryPolicy, MetafieldType, WeightUnit
    - MediaContentType, MediaStatus, CurrencyCode
    - InventoryReason, InventoryQuantityName

Note:
    This module is SEPARATE from the root ``enums.py`` which contains
    **configuration/infrastructure enums** (OutputFormat, DeployTarget, CacheBackend).

    Import these enums from ``models`` for public use::

        from lib_shopify_graphql.models import ProductStatus, InventoryPolicy
"""

from __future__ import annotations

from .._compat import StrEnum


class ProductStatus(StrEnum):
    """Product publication status in Shopify.

    Attributes:
        ACTIVE: Product is visible to customers.
        ARCHIVED: Product is hidden and not for sale.
        DRAFT: Product is being prepared and not yet published.
    """

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DRAFT = "DRAFT"


class InventoryPolicy(StrEnum):
    """Policy for selling when out of stock.

    Attributes:
        DENY: Stop selling when out of stock.
        CONTINUE: Continue selling when out of stock.
    """

    DENY = "DENY"
    CONTINUE = "CONTINUE"


class MetafieldType(StrEnum):
    """Shopify metafield data types.

    Attributes:
        SINGLE_LINE_TEXT_FIELD: Single line text.
        MULTI_LINE_TEXT_FIELD: Multi-line text.
        NUMBER_INTEGER: Integer number.
        NUMBER_DECIMAL: Decimal number.
        BOOLEAN: True/False value.
        DATE: Date without time.
        DATE_TIME: Date with time.
        JSON: JSON object.
        COLOR: Color value.
        URL: URL value.
        MONEY: Monetary value.
        DIMENSION: Physical dimension.
        VOLUME: Volume measurement.
        WEIGHT: Weight measurement.
        RATING: Rating value.
        RICH_TEXT_FIELD: Rich text content.
        LINK: Link/URL with text.
        FILE_REFERENCE: Reference to a file.
        PRODUCT_REFERENCE: Reference to a product.
        VARIANT_REFERENCE: Reference to a variant.
        COLLECTION_REFERENCE: Reference to a collection.
        PAGE_REFERENCE: Reference to a page.
        METAOBJECT_REFERENCE: Reference to a metaobject.
        ARTICLE_REFERENCE: Reference to an article.
        MIXED_REFERENCE: Mixed reference type.
        LIST_SINGLE_LINE_TEXT_FIELD: List of single line text.
        LIST_FILE_REFERENCE: List of file references.
        LIST_PRODUCT_REFERENCE: List of product references.
        LIST_VARIANT_REFERENCE: List of variant references.
        LIST_COLLECTION_REFERENCE: List of collection references.
        LIST_PAGE_REFERENCE: List of page references.
        LIST_METAOBJECT_REFERENCE: List of metaobject references.
        LIST_ARTICLE_REFERENCE: List of article references.
        LIST_MIXED_REFERENCE: List of mixed references.
        LIST_NUMBER_INTEGER: List of integers.
        LIST_NUMBER_DECIMAL: List of decimals.
        LIST_COLOR: List of colors.
        LIST_DATE: List of dates.
        LIST_DATE_TIME: List of datetimes.
        LIST_URL: List of URLs.
        LIST_LINK: List of links.
    """

    # Basic types
    SINGLE_LINE_TEXT_FIELD = "single_line_text_field"
    MULTI_LINE_TEXT_FIELD = "multi_line_text_field"
    NUMBER_INTEGER = "number_integer"
    NUMBER_DECIMAL = "number_decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATE_TIME = "date_time"
    JSON = "json"
    COLOR = "color"
    URL = "url"
    MONEY = "money"
    DIMENSION = "dimension"
    VOLUME = "volume"
    WEIGHT = "weight"
    RATING = "rating"
    RICH_TEXT_FIELD = "rich_text_field"
    LINK = "link"

    # Reference types
    FILE_REFERENCE = "file_reference"
    PRODUCT_REFERENCE = "product_reference"
    VARIANT_REFERENCE = "variant_reference"
    COLLECTION_REFERENCE = "collection_reference"
    PAGE_REFERENCE = "page_reference"
    METAOBJECT_REFERENCE = "metaobject_reference"
    ARTICLE_REFERENCE = "article_reference"
    MIXED_REFERENCE = "mixed_reference"

    # List types
    LIST_SINGLE_LINE_TEXT_FIELD = "list.single_line_text_field"
    LIST_FILE_REFERENCE = "list.file_reference"
    LIST_PRODUCT_REFERENCE = "list.product_reference"
    LIST_VARIANT_REFERENCE = "list.variant_reference"
    LIST_COLLECTION_REFERENCE = "list.collection_reference"
    LIST_PAGE_REFERENCE = "list.page_reference"
    LIST_METAOBJECT_REFERENCE = "list.metaobject_reference"
    LIST_ARTICLE_REFERENCE = "list.article_reference"
    LIST_MIXED_REFERENCE = "list.mixed_reference"
    LIST_NUMBER_INTEGER = "list.number_integer"
    LIST_NUMBER_DECIMAL = "list.number_decimal"
    LIST_COLOR = "list.color"
    LIST_DATE = "list.date"
    LIST_DATE_TIME = "list.date_time"
    LIST_URL = "list.url"
    LIST_LINK = "list.link"


class WeightUnit(StrEnum):
    """Units for product/variant weight.

    Attributes:
        GRAMS: Weight in grams.
        KILOGRAMS: Weight in kilograms.
        OUNCES: Weight in ounces.
        POUNDS: Weight in pounds.
    """

    GRAMS = "GRAMS"
    KILOGRAMS = "KILOGRAMS"
    OUNCES = "OUNCES"
    POUNDS = "POUNDS"


class MediaContentType(StrEnum):
    """Content type for product media in Shopify.

    Attributes:
        IMAGE: Image media (JPG, PNG, GIF, WEBP).
        VIDEO: Video media.
        EXTERNAL_VIDEO: External video (YouTube, Vimeo).
        MODEL_3D: 3D model file.
    """

    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    EXTERNAL_VIDEO = "EXTERNAL_VIDEO"
    MODEL_3D = "MODEL_3D"


class MediaStatus(StrEnum):
    """Processing status for product media in Shopify.

    Attributes:
        PROCESSING: Media is being processed.
        READY: Media is ready for display.
        FAILED: Media processing failed.
        UPLOADED: Media has been uploaded but not yet processed.
    """

    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    UPLOADED = "UPLOADED"


class CurrencyCode(StrEnum):
    """Common ISO 4217 currency codes used in Shopify.

    Attributes:
        USD: US Dollar.
        EUR: Euro.
        GBP: British Pound.
        CAD: Canadian Dollar.
        AUD: Australian Dollar.
        JPY: Japanese Yen.
        CHF: Swiss Franc.
        CNY: Chinese Yuan.
        INR: Indian Rupee.
        MXN: Mexican Peso.
    """

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"
    AUD = "AUD"
    JPY = "JPY"
    CHF = "CHF"
    CNY = "CNY"
    INR = "INR"
    MXN = "MXN"


class InventoryReason(StrEnum):
    """Reason for inventory changes in Shopify.

    Attributes:
        CORRECTION: Manual stock count correction.
        RECEIVED: Stock received from supplier.
        DAMAGED: Stock damaged and removed.
        SHRINKAGE: Stock loss due to theft/loss.
        PROMOTION_OR_DONATION: Given away.
        MOVEMENT_CREATED: Movement created.
        MOVEMENT_UPDATED: Movement updated.
        MOVEMENT_RECEIVED: Movement received.
        MOVEMENT_CANCELED: Movement canceled.
        QUALITY_CONTROL: Quality control adjustment.
        CYCLE_COUNT_AVAILABLE: Cycle count for available.
        OTHER: Other reason.
    """

    CORRECTION = "correction"
    RECEIVED = "received"
    DAMAGED = "damaged"
    SHRINKAGE = "shrinkage"
    PROMOTION_OR_DONATION = "promotion_or_donation"
    MOVEMENT_CREATED = "movement_created"
    MOVEMENT_UPDATED = "movement_updated"
    MOVEMENT_RECEIVED = "movement_received"
    MOVEMENT_CANCELED = "movement_canceled"
    QUALITY_CONTROL = "quality_control"
    CYCLE_COUNT_AVAILABLE = "cycle_count_available"
    OTHER = "other"


class InventoryQuantityName(StrEnum):
    """Name for inventory quantity types in Shopify.

    Attributes:
        AVAILABLE: Quantity available for sale.
        INCOMING: Incoming quantity (in transit).
        COMMITTED: Quantity committed to orders.
        DAMAGED: Damaged quantity.
        ON_HAND: Total on-hand quantity.
        QUALITY_CONTROL: Quantity in quality control.
        RESERVED: Reserved quantity.
        SAFETY_STOCK: Safety stock quantity.
    """

    AVAILABLE = "available"
    INCOMING = "incoming"
    COMMITTED = "committed"
    DAMAGED = "damaged"
    ON_HAND = "on_hand"
    QUALITY_CONTROL = "quality_control"
    RESERVED = "reserved"
    SAFETY_STOCK = "safety_stock"


__all__ = [
    "CurrencyCode",
    "InventoryPolicy",
    "InventoryQuantityName",
    "InventoryReason",
    "MediaContentType",
    "MediaStatus",
    "MetafieldType",
    "ProductStatus",
    "WeightUnit",
]
