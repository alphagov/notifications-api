from app.models import ProviderStatistics


def get_provider_statistics(service, provider):
    return ProviderStatistics.query.filter_by(service=service, provider=provider).one()
