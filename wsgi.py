from app import create_app
import os

application = create_app(os.getenv('NOTIFICATIONS_API_ENVIRONMENT') or 'development')

if __name__ == "__main__":
        application.run()
