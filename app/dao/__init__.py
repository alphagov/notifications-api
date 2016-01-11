from sqlalchemy.exc import SQLAlchemyError


# Should I use SQLAlchemyError?
class DAOException(SQLAlchemyError):
    pass
