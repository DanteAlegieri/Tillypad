from datetime import date
from typing import Any

from app.db.sql_server import SqlServer
from app.recommendations.engine import RecommendationEngine
from app.repositories.marketing_repository import MarketingRepository
from app.services.menu_analytics_service import MenuAnalyticsService
from app.services.sales_service import SalesService
from app.services.live_analyst_service import LiveAnalystService


class RecommendationService:
    def __init__(self) -> None:
        self.engine = RecommendationEngine()
        self.marketing_repository = MarketingRepository(SqlServer())
        self.live_analyst = LiveAnalystService()

    def dashboard(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        menu = MenuAnalyticsService().dashboard(date_from, date_to)
        sales = SalesService().dashboard(
            menu["date_from"],
            menu["date_to"],
        )
        opportunities = self.marketing_repository.basket_opportunities(
            menu["date_from"],
            menu["date_to"],
        )

        service_positions = {
            "доставка",
            "доставка курьером",
            "стоимость доставки",
            "самовывоз",
        }
        opportunities = [
            row for row in opportunities
            if str(row.get("base_item_name") or "").strip().lower()
               not in service_positions
            and str(row.get("pair_item_name") or "").strip().lower()
               not in service_positions
        ]

        menu_recommendations = self.engine.menu_recommendations(
            menu["items"],
            menu["date_from"],
            menu["date_to"],
        )
        sales_recommendations = self.engine.sales_recommendations(sales)
        marketing_recommendations = self.engine.marketing_recommendations(
            opportunities
        )

        recommendations = self.engine.combine(
            sales_recommendations,
            marketing_recommendations,
            menu_recommendations,
            limit=24,
        )

        priorities = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        for item in recommendations:
            priorities[item["priority"]] = (
                priorities.get(item["priority"], 0) + 1
            )

        estimated_potential = sum(
            float(row.get("estimated_potential") or 0)
            for row in opportunities
        )
        live_analyst = self.live_analyst.build(
            menu["date_from"],
            menu["date_to"],
            opportunities,
        )

        return {
            "date_from": menu["date_from"],
            "date_to": menu["date_to"],
            "recommendations": recommendations,
            "priorities": priorities,
            "opportunities": opportunities,
            "estimated_potential": estimated_potential,
            "live_analyst": live_analyst,
            "menu_health": round(
                sum(
                    float(item.get("index_score") or 0)
                    for item in menu["items"]
                ) / len(menu["items"])
            ) if menu["items"] else 0,
            "sources": {
                "manager": len(sales_recommendations),
                "technologist": len(menu_recommendations),
                "marketer": len(marketing_recommendations),
            },
        }
