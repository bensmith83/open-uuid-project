from fastapi import FastAPI, HTTPException, Depends, Query, UploadFile, File
from sqlalchemy import create_engine, Column, String, Integer, Enum, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, backref
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from uuid import uuid4 as generate_uuid
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import enum
from typing import List
import logging

# Add near the top of the file
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Bluetooth Characteristics Mapper")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
SQLALCHEMY_DATABASE_URL = "sqlite:///./bluetooth_characteristics.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Enum for BLE attribute types
class BLEAttributeType(str, enum.Enum):
    SERVICE = "service"
    CHARACTERISTIC = "characteristic"
    DESCRIPTOR = "descriptor"

# Database Models
class BLEAttribute(Base):
    __tablename__ = "ble_attributes"
    
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, index=True)
    vendor = Column(String, index=True)
    model = Column(String, index=True)
    description = Column(String)
    attribute_type = Column(Enum(BLEAttributeType))
    service_uuid = Column(String, ForeignKey('ble_attributes.uuid'), nullable=True)
    sample_data = Column(String, nullable=True)
    can_read = Column(Boolean, default=False)
    can_write = Column(Boolean, default=False)
    can_indicate = Column(Boolean, default=False)
    can_notify = Column(Boolean, default=False)
    comment = Column(String, nullable=True)
    
    # Updated relationship definition
    children = relationship(
        "BLEAttribute",
        backref=backref("parent", remote_side=[uuid]),
        cascade="all, delete",  # Changed from "all, delete-orphan"
        lazy="selectin",
        foreign_keys=[service_uuid]  # Add this to be explicit about the foreign key
    )

# Pydantic models for request/response
class BLEAttributeBase(BaseModel):
    uuid: str
    vendor: str
    model: str
    description: str
    attribute_type: BLEAttributeType
    service_uuid: str | None = None
    sample_data: str | None = None
    can_read: bool = False
    can_write: bool = False
    can_indicate: bool = False
    can_notify: bool = False
    comment: str | None = None

class BLEAttributeCreate(BLEAttributeBase):
    pass

class BLEAttributeResponse(BLEAttributeBase):
    id: int
    
    class Config:
        orm_mode = True
        from_attributes = True

class BLEAttributeNestedResponse(BLEAttributeResponse):
    children: List[BLEAttributeResponse] = []
    
    class Config:
        orm_mode = True
        from_attributes = True

# Create database tables
Base.metadata.create_all(bind=engine)

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# API Routes
@app.post("/attributes/", response_model=BLEAttributeResponse)
async def create_attribute(attribute: BLEAttributeCreate, db: SessionLocal = Depends(get_db)):
    # Require service_uuid for characteristics and descriptors
    if attribute.attribute_type != BLEAttributeType.SERVICE and not attribute.service_uuid:
        raise HTTPException(
            status_code=400, 
            detail="Characteristics and descriptors must be associated with a service"
        )
    
    # Validate service reference
    if attribute.service_uuid:
        service = db.query(BLEAttribute).filter(
            BLEAttribute.uuid == attribute.service_uuid,
            BLEAttribute.attribute_type == BLEAttributeType.SERVICE
        ).first()
        if not service:
            raise HTTPException(status_code=400, detail="Referenced service not found")
    
    db_attribute = BLEAttribute(**attribute.dict())
    db.add(db_attribute)
    try:
        db.commit()
        db.refresh(db_attribute)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="UUID already exists")
    return db_attribute

@app.get("/attributes/", response_model=List[BLEAttributeNestedResponse])
async def read_attributes(
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
    attribute_type: BLEAttributeType | None = None,
    show_all: bool = True,
    db: SessionLocal = Depends(get_db)
):
    query = db.query(BLEAttribute)
    
    if search:
        search = f"%{search}%"
        query = query.filter(
            (BLEAttribute.uuid.ilike(search)) |
            (BLEAttribute.vendor.ilike(search)) |
            (BLEAttribute.model.ilike(search)) |
            (BLEAttribute.description.ilike(search))
        )
    
    if attribute_type:
        query = query.filter(BLEAttribute.attribute_type == attribute_type)
    elif not show_all:
        query = query.filter(BLEAttribute.service_uuid == None)
    
    return query.offset(skip).limit(limit).all()

@app.get("/attributes/{uuid}", response_model=BLEAttributeNestedResponse)
async def read_attribute(uuid: str, db: SessionLocal = Depends(get_db)):
    attribute = db.query(BLEAttribute).filter(BLEAttribute.uuid == uuid).first()
    if attribute is None:
        raise HTTPException(status_code=404, detail="Attribute not found")
    return attribute

@app.get("/")
async def read_root():
    return FileResponse('index.html')

@app.post("/upload-log/")
async def upload_log(file: UploadFile = File(...)):
    content = await file.read()
    # Here you would process the log file
    # This is a placeholder - you'll need to implement the actual log parsing logic
    try:
        text_content = content.decode()
        # Process the log content here
        return {"message": "Log file processed successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing log: {str(e)}")

@app.patch("/attributes/{uuid}", response_model=BLEAttributeResponse)
async def update_attribute(uuid: str, update: dict, db: SessionLocal = Depends(get_db)):
    attribute = db.query(BLEAttribute).filter(BLEAttribute.uuid == uuid).first()
    if attribute is None:
        raise HTTPException(status_code=404, detail="Attribute not found")
    
    for key, value in update.items():
        setattr(attribute, key, value)
    
    try:
        db.commit()
        db.refresh(attribute)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Update failed")
    return attribute

@app.delete("/attributes/{uuid}")
async def delete_attribute(uuid: str, db: SessionLocal = Depends(get_db)):
    attribute = db.query(BLEAttribute).filter(BLEAttribute.uuid == uuid).first()
    if attribute is None:
        raise HTTPException(status_code=404, detail="Attribute not found")
    
    # Check if it's a service with characteristics
    if attribute.attribute_type == BLEAttributeType.SERVICE and attribute.children:
        char_count = len(attribute.children)
        raise HTTPException(
            status_code=409, 
            detail=f"Service has {char_count} characteristic(s). Use force_delete=true to delete the service and all its characteristics."
        )
    
    db.delete(attribute)
    try:
        db.commit()
        return {"message": "Attribute deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/attributes/{uuid}/force")
async def force_delete_attribute(uuid: str, db: SessionLocal = Depends(get_db)):
    logger.info(f"Attempting force delete of attribute {uuid}")
    try:
        attribute = db.query(BLEAttribute).filter(BLEAttribute.uuid == uuid).first()
        logger.info(f"Found attribute: {attribute is not None}")
        
        if attribute is None:
            logger.error(f"Attribute {uuid} not found")
            raise HTTPException(status_code=404, detail="Attribute not found")
        
        logger.info(f"Attribute type: {attribute.attribute_type}")
        logger.info(f"Children count: {len(attribute.children)}")
        
        # Get count of children before deletion
        child_count = len(attribute.children)
        logger.info(f"Found {child_count} children to delete")
        
        # Explicitly delete each child
        for child in list(attribute.children):
            logger.info(f"Deleting child {child.uuid}")
            result = db.query(BLEAttribute).filter(BLEAttribute.uuid == child.uuid).delete()
            logger.info(f"Delete result for child: {result}")
        
        # Delete the service
        logger.info(f"Deleting service {uuid}")
        result = db.query(BLEAttribute).filter(BLEAttribute.uuid == uuid).delete()
        logger.info(f"Delete result for service: {result}")
        
        db.commit()
        logger.info("Deletion completed successfully")
        return {"message": f"Deleted service and {child_count} characteristics"}
    except Exception as e:
        logger.error(f"Error during deletion: {str(e)}")
        logger.exception(e)  # This will log the full stack trace
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/attributes/{uuid}/orphan")
async def orphan_delete_attribute(uuid: str, db: SessionLocal = Depends(get_db)):
    logger.info(f"Attempting to orphan children of service {uuid}")
    attribute = db.query(BLEAttribute).filter(BLEAttribute.uuid == uuid).first()
    if attribute is None:
        raise HTTPException(status_code=404, detail="Attribute not found")
    
    if attribute.attribute_type != BLEAttributeType.SERVICE:
        raise HTTPException(status_code=400, detail="Can only orphan characteristics from services")
    
    try:
        # Get count of children before orphaning
        child_count = len(attribute.children)
        logger.info(f"Found {child_count} children to orphan")
        
        # Explicitly update each child
        for child in list(attribute.children):
            logger.info(f"Orphaning child {child.uuid}")
            db.query(BLEAttribute).filter(BLEAttribute.uuid == child.uuid).update(
                {"service_uuid": None}
            )
        
        # Delete the service
        logger.info(f"Deleting service {uuid}")
        db.query(BLEAttribute).filter(BLEAttribute.uuid == uuid).delete()
        
        db.commit()
        logger.info("Orphaning completed successfully")
        return {"message": f"Deleted service and orphaned {child_count} characteristics"}
    except Exception as e:
        logger.error(f"Error during orphaning: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# Add this new model for log parsing
class LogParseRequest(BaseModel):
    log_text: str
    vendor: str | None = None
    model: str | None = None
    description: str | None = None

@app.post("/parse-log/")
async def parse_log(
    request: LogParseRequest,
    db: SessionLocal = Depends(get_db)
):
    services = {}
    characteristics = {}
    current_service = None
    
    # Parse the log line by line
    for line in request.log_text.split('\n'):
        if "Discovered" in line and "Services" in line:
            # Extract service UUIDs - handle multiple services in one line
            service_part = line.split('Discovered ')[1].split(' Services')[0].strip()
            # Split by comma and handle potential 'and' in the last item
            if ',' in service_part:
                service_items = service_part.split(',')
                if ' and ' in service_items[-1]:
                    last_items = service_items[-1].split(' and ')
                    service_items = service_items[:-1] + last_items
            else:
                service_items = service_part.split(' and ')
            
            # Process each service
            for service_item in service_items:
                service_item = service_item.strip()
                # If it's a UUID, use it directly, otherwise use it as description
                if any(c in service_item for c in '0123456789ABCDEF-'):
                    uuid = service_item
                    description = f'Service {uuid}'
                else:
                    # For named services without UUID, generate a placeholder UUID
                    uuid = str(generate_uuid())
                    description = service_item
                
                services[uuid] = {
                    'uuid': uuid,
                    'vendor': request.vendor,
                    'model': request.model,
                    'description': description,
                    'attribute_type': 'service',
                    'comment': f'Automatically parsed from log: {request.description or "No description provided"}'
                }
                current_service = uuid
        
        elif "Discovered" in line and "Characteristics" in line:
            # Extract characteristic UUIDs and names
            char_part = line.split('Discovered ')[1].split(' Characteristics')[0]
            
            # Handle both comma-separated and 'and' separated lists
            if ',' in char_part:
                # Split by comma and handle potential 'and' in the last item
                char_items = char_part.split(',')
                if ' and ' in char_items[-1]:
                    last_items = char_items[-1].split(' and ')
                    char_items = char_items[:-1] + last_items
            else:
                # Handle simple 'and' separated items
                char_items = char_part.split(' and ')
            
            # Clean up each characteristic
            for char_item in char_items:
                char_item = char_item.strip()
                if any(c in char_item for c in '0123456789ABCDEF-'):
                    char_uuid = char_item
                    description = f'Characteristic {char_uuid}'
                else:
                    # Use the renamed uuid import
                    char_uuid = str(generate_uuid())
                    description = char_item
                
                characteristics[char_uuid] = {
                    'uuid': char_uuid,
                    'vendor': request.vendor,
                    'model': request.model,
                    'description': description,
                    'service_uuid': current_service,
                    'attribute_type': 'characteristic',
                    'can_read': False,
                    'can_write': False,
                    'can_notify': False,
                    'can_indicate': False,
                    'comment': f'Automatically parsed from log: {request.description or "No description provided"}'
                }
        
        # Parse characteristic properties
        elif "Setting Boolean true for Notifying Characteristic" in line:
            uuid = line.split('Characteristic ')[1].strip()
            if uuid in characteristics:
                characteristics[uuid]['can_notify'] = True
                
        elif "Writing value" in line and "to" in line:
            uuid = line.split('to ')[1].split(' Characteristic')[0].strip()
            if uuid in characteristics:
                characteristics[uuid]['can_write'] = True
                
        elif "Updated Value of Characteristic" in line:
            parts = line.split('Characteristic ')[1].split(' to ')
            uuid = parts[0].strip()
            sample_data = parts[1].strip()
            if uuid in characteristics:
                characteristics[uuid]['can_read'] = True
                characteristics[uuid]['sample_data'] = sample_data

    # Create/update database entries
    created_items = []
    try:
        # First create services
        for service_data in services.values():
            service = BLEAttribute(**service_data)
            db.add(service)
            created_items.append(service_data)
        
        # Then create characteristics
        for char_data in characteristics.values():
            char = BLEAttribute(**char_data)
            db.add(char)
            created_items.append(char_data)
            
        db.commit()
        
        return {
            "message": "Log parsed successfully",
            "created_items": created_items
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/sample-data")
async def create_sample_data(db: SessionLocal = Depends(get_db)):
    sample_data = [
        # Standard Bluetooth Services (16-bit UUIDs)
        {
            "uuid": "1800",
            "vendor": "Bluetooth SIG",
            "model": "Generic",
            "description": "Generic Access",
            "attribute_type": "service",
            "comment": "Defines device name, appearance, and connection parameters"
        },
        {
            "uuid": "2A00",
            "vendor": "Bluetooth SIG",
            "model": "Generic",
            "description": "Device Name",
            "attribute_type": "characteristic",
            "service_uuid": "1800",
            "can_read": True,
            "can_write": True,
            "sample_data": "Fitbit Charge 5",
            "comment": "Human readable device name"
        },

        # Apple Device (128-bit UUIDs)
        {
            "uuid": "9FA480E0-4967-4542-9390-D343DC5D04AE",
            "vendor": "Apple Inc.",
            "model": "AirPods Pro",
            "description": "Apple Notification Center Service",
            "attribute_type": "service",
            "comment": "Handles iOS notifications"
        },
        {
            "uuid": "9FBF120D-6301-42D9-8C58-25E699A21DBD",
            "vendor": "Apple Inc.",
            "model": "AirPods Pro",
            "description": "Notification Source",
            "attribute_type": "characteristic",
            "service_uuid": "9FA480E0-4967-4542-9390-D343DC5D04AE",
            "can_notify": True,
            "sample_data": "0x01020304",
            "comment": "Notifies about incoming notifications"
        },

        # Fitbit Device
        {
            "uuid": "ADABFB00-6E7D-4601-BDA2-BFFAA68956BA",
            "vendor": "Fitbit",
            "model": "Charge 5",
            "description": "Fitbit Service",
            "attribute_type": "service",
            "comment": "Main Fitbit service for fitness tracking"
        },
        {
            "uuid": "ADABFB01-6E7D-4601-BDA2-BFFAA68956BA",
            "vendor": "Fitbit",
            "model": "Charge 5",
            "description": "Heart Rate",
            "attribute_type": "characteristic",
            "service_uuid": "ADABFB00-6E7D-4601-BDA2-BFFAA68956BA",
            "can_read": True,
            "can_notify": True,
            "sample_data": "72",
            "comment": "Real-time heart rate monitoring"
        },

        # Nordic Semiconductor DFU
        {
            "uuid": "FE59",
            "vendor": "Nordic Semiconductor",
            "model": "nRF52",
            "description": "Secure DFU Service",
            "attribute_type": "service",
            "comment": "Device Firmware Update service"
        },
        {
            "uuid": "8EC90001-F315-4F60-9FB8-838830DAEA50",
            "vendor": "Nordic Semiconductor",
            "model": "nRF52",
            "description": "DFU Control Point",
            "attribute_type": "characteristic",
            "service_uuid": "FE59",
            "can_write": True,
            "can_notify": True,
            "comment": "Control point for firmware updates"
        },

        # Xiaomi Mi Band
        {
            "uuid": "FEE0",
            "vendor": "Xiaomi",
            "model": "Mi Band 6",
            "description": "Mi Band Service",
            "attribute_type": "service",
            "comment": "Main service for Mi Band device"
        },
        {
            "uuid": "FEE1",
            "vendor": "Xiaomi",
            "model": "Mi Band 6",
            "description": "Activity Data",
            "attribute_type": "characteristic",
            "service_uuid": "FEE0",
            "can_read": True,
            "can_notify": True,
            "sample_data": "Steps: 8547",
            "comment": "Activity and fitness tracking data"
        },

        # Texas Instruments Sensor Tag
        {
            "uuid": "F000AA00-0451-4000-B000-000000000000",
            "vendor": "Texas Instruments",
            "model": "CC2650 SensorTag",
            "description": "Temperature Service",
            "attribute_type": "service",
            "comment": "IR and Ambient Temperature Sensing"
        },
        {
            "uuid": "F000AA01-0451-4000-B000-000000000000",
            "vendor": "Texas Instruments",
            "model": "CC2650 SensorTag",
            "description": "Temperature Data",
            "attribute_type": "characteristic",
            "service_uuid": "F000AA00-0451-4000-B000-000000000000",
            "can_read": True,
            "can_notify": True,
            "sample_data": "23.5",
            "comment": "Temperature sensor readings"
        }
    ]

    # Add more variations of real-world devices
    vendors = [
        {
            "name": "Samsung",
            "model": "Galaxy Watch 4",
            "uuid_prefix": "6C53DB",
            "services": [
                ("Health Service", "Activity tracking and health monitoring"),
                ("Notification Service", "Handles phone notifications"),
                ("Battery Service", "Battery level monitoring")
            ]
        },
        {
            "name": "Garmin",
            "model": "Forerunner 945",
            "uuid_prefix": "395F8D",
            "services": [
                ("Running Dynamics", "Advanced running metrics"),
                ("Training Status", "Training load and recovery"),
                ("Pulse Ox", "Blood oxygen monitoring")
            ]
        },
        {
            "name": "Polar",
            "model": "H10",
            "uuid_prefix": "FB005C",
            "services": [
                ("Heart Rate Service", "ECG-based heart rate monitoring"),
                ("Battery Service", "Battery status"),
                ("Firmware Service", "Device firmware updates")
            ]
        }
    ]

    # Generate variations with both short and long UUIDs
    for i, vendor in enumerate(vendors):
        for j, (service_name, service_desc) in enumerate(vendor["services"]):
            # Use both short and long UUIDs
            if i % 2 == 0:
                # Short UUID for even numbered vendors
                service_uuid = f"{vendor['uuid_prefix']}{j:02d}"
                char_uuid = f"{vendor['uuid_prefix']}{j:02d}1"
            else:
                # Long UUID for odd numbered vendors
                service_uuid = f"{vendor['uuid_prefix']}-{j:04d}-4000-B000-{i:012d}"
                char_uuid = f"{vendor['uuid_prefix']}-{j:04d}-4000-B000-{i:012d}0001"

            sample_data.extend([
                {
                    "uuid": service_uuid,
                    "vendor": vendor["name"],
                    "model": vendor["model"],
                    "description": service_name,
                    "attribute_type": "service",
                    "comment": service_desc
                },
                {
                    "uuid": char_uuid,
                    "vendor": vendor["name"],
                    "model": vendor["model"],
                    "description": f"{service_name} Data",
                    "attribute_type": "characteristic",
                    "service_uuid": service_uuid,
                    "can_read": True,
                    "can_notify": True,
                    "sample_data": f"Sample data for {service_name}",
                    "comment": f"Main characteristic for {service_name}"
                }
            ])

    created_count = 0
    skipped_count = 0
    try:
        # First create services
        for item in sample_data:
            # Check if item already exists
            existing = db.query(BLEAttribute).filter(BLEAttribute.uuid == item["uuid"]).first()
            if not existing:
                if item["attribute_type"] == "service":
                    db_item = BLEAttribute(**item)
                    db.add(db_item)
                    created_count += 1
            else:
                skipped_count += 1
        db.commit()

        # Then create characteristics
        for item in sample_data:
            existing = db.query(BLEAttribute).filter(BLEAttribute.uuid == item["uuid"]).first()
            if not existing:
                if item["attribute_type"] == "characteristic":
                    db_item = BLEAttribute(**item)
                    db.add(db_item)
                    created_count += 1
            else:
                skipped_count += 1
        db.commit()

        return {
            "message": f"Sample data processed: {created_count} items created, {skipped_count} items skipped"
        }
    except Exception as e:
        logger.error(f"Error creating sample data: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/clear-sample-data")
async def clear_sample_data(db: SessionLocal = Depends(get_db)):
    try:
        # Delete all attributes where vendor is "Bluetooth SIG" or "Custom Vendor"
        db.query(BLEAttribute).filter(
            (BLEAttribute.vendor == "Bluetooth SIG") | 
            (BLEAttribute.vendor == "Custom Vendor")
        ).delete()
        db.commit()
        return {"message": "Sample data cleared successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
