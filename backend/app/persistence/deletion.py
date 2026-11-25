from sqlalchemy import delete, select, tuple_


def delete_checked(db, model, *conditions):
    """Lock selected primary keys and delete exactly those rows in the same transaction."""
    columns = tuple(model.__table__.primary_key.columns)
    keys = db.execute(select(*columns).where(*conditions).with_for_update()).all()
    for start in range(0, len(keys), 500):
        batch = keys[start:start + 500]
        predicate = columns[0].in_([row[0] for row in batch]) if len(columns) == 1 else tuple_(*columns).in_([tuple(row) for row in batch])
        db.execute(delete(model).where(predicate))
