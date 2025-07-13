from enum import Enum

class DeliveryType(str, Enum):
    clinical_waste = "clinical_waste"
    documents = "documents"
    equipment = "equipment"
    samples = "samples"
    other = "other"

class InvoiceStatus(str, Enum):
    unpaid = "unpaid"
    paid = "paid"
    overdue = "overdue"
    
class OrganizationType(str,Enum):
    clinic = "clinic"
    waste_company = "waste_company"    

