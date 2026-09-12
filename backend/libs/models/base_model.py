from django.db.models import DateTimeField, Model


class BaseModel(Model):
    created_at = DateTimeField(auto_now_add=True, db_index=True)
    updated_at = DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True
