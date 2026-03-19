# ---------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License. See LICENSE in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Graph API scenario generation service."""

import logging
from typing import Dict, Any, Optional, List

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

from src.config import config

logger = logging.getLogger(__name__)


class GraphScenarioGenerator:
    """Generates training scenarios based on Microsoft Graph API data."""

    def __init__(self):
        """Initialize the Graph scenario generator."""
        self.openai_client = self._initialize_openai_client()

    def _initialize_openai_client(self) -> Optional[AzureOpenAI]:
        """Initialize the Azure OpenAI client for scenario generation.

        Uses API key if configured, otherwise falls back to managed identity
        via DefaultAzureCredential.
        """
        try:
            endpoint = config["azure_openai_endpoint"]

            if not endpoint:
                logger.warning("Azure OpenAI not configured for scenario generation")
                return None

            api_key = config["azure_openai_api_key"]
            if api_key:
                return AzureOpenAI(
                    api_version=config["api_version"],
                    azure_endpoint=endpoint,
                    api_key=api_key,
                )
            else:
                token_provider = get_bearer_token_provider(
                    DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
                )
                return AzureOpenAI(
                    api_version=config["api_version"],
                    azure_endpoint=endpoint,
                    azure_ad_token_provider=token_provider,
                )
        except Exception as e:
            logger.error("Failed to initialize OpenAI client for scenarios: %s", e)
            return None

    def generate_scenario_from_graph(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a scenario based on Microsoft Graph API data.

        Args:
            graph_data: The Graph API response data

        Returns:
            Dict[str, Any]: Generated scenario
        """
        meetings: List[Dict[str, Any]] = []
        if "value" in graph_data:
            for event in graph_data["value"][:3]:
                subject = event.get("subject", "Meeting")
                attendees = [attendee["emailAddress"]["name"] for attendee in event.get("attendees", [])[:3]]
                meetings.append({"subject": subject, "attendees": attendees})

        scenario_content = self._create_graph_scenario_content(meetings)

        first_sentence = scenario_content.split(".")[0] + "."
        if len(first_sentence) > 100:
            first_sentence = first_sentence[:100] + "..."

        return {
            "id": "graph-generated",
            "name": "Your Personalised Customer Scenario",
            "description": first_sentence,
            "messages": [{"content": scenario_content}],
            "model": config["model_deployment_name"],
            "modelParameters": {"temperature": 0.7, "max_tokens": 2000},
            "generated_from_graph": True,
        }

    def _format_meeting_list(self, meetings: List[Dict[str, Any]]) -> str:
        """Format the list of meetings for display."""
        return "\n".join(f"- {meeting['subject']} with {', '.join(meeting['attendees'][:3])}" for meeting in meetings)

    def _create_graph_scenario_content(self, meetings: List[Dict[str, Any]]) -> str:
        """Create scenario content based on meetings using OpenAI."""
        if not meetings:
            return self._get_fallback_scenario_content()

        if not self.openai_client:
            logger.warning("OpenAI client not available, using fallback scenario")
            return self._get_fallback_scenario_content()

        prompt = self._build_scenario_generation_prompt(meetings)

        response = self.openai_client.chat.completions.create(
            model=config["model_deployment_name"],
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert at creating realistic role-play scenarios for insurance customer service training at NFU Mutual. "
                        "Generate engaging, professional scenarios that help advisers prepare for real customer interactions "
                        "including enquiries, complaints, renewals, and claims discussions."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1500,
        )

        content = response.choices[0].message.content
        generated_content = content.strip() if content is not None else ""
        return generated_content

    def _build_scenario_generation_prompt(self, meetings: List[Dict[str, Any]]) -> str:
        """Build the prompt for OpenAI scenario generation."""
        return (
            "Generate a role-play scenario to help an NFU Mutual adviser prepare for upcoming customer interactions. "
            "Based on their calendar, the following meetings are scheduled:\n\n"
            f"{self._format_meeting_list(meetings)}\n\n"
            "Create a realistic customer service practice scenario for an upcoming interaction using the following "
            "structure:\n\n"
            "1. **Context**: Start with a quick summary of the customer situation.\n"
            "2. **Character**: Define the customer the trainee will interact with (name, background, insurance needs). "
            "Include relevant personal details such as occupation, property type, and family circumstances.\n"
            "3. **Behavioral Guidelines (Act Human)**: Outline how the customer should behave in conversation "
            "(e.g., friendly, frustrated, anxious, confused, loyal).\n"
            "4. **Character Profile**: Provide background that shapes the customer's perspective and insurance needs.\n"
            "5. **Key Concerns**: List 2–3 specific concerns, questions, or issues the customer should "
            "raise during the conversation. These should be realistic for UK insurance customers.\n"
            "6. **Instruction**: End by telling the AI to roleplay as this customer, responding naturally.\n\n"
            "**Example output:**\n\n"
            "Renewal discussion with a long-standing home insurance customer.\n\n"
            "You are **Margaret Davies, a 62-year-old retired teacher** living in a detached period property in "
            "rural Herefordshire. You've been an NFU Mutual customer for 18 years.\n\n"
            "**BEHAVIORAL GUIDELINES (Act Human):**\n\n"
            "* Speak warmly but be direct about concerns\n"
            "* Reference your loyalty as a long-standing customer\n"
            "* Show concern about rising costs on a fixed retirement income\n\n"
            "**YOUR CHARACTER PROFILE:**\n\n"
            "* Retired secondary school headteacher, lives alone since husband passed\n"
            "* Grade II listed cottage with thatched roof — specialist cover needed\n"
            "* Values the personal service from her local NFU Mutual agency\n\n"
            "**KEY CONCERNS TO RAISE:**\n\n"
            "1. Premium has increased again — can you explain why and is there anything that can be done?\n"
            "2. The cottage needs rewiring — will this affect my cover?\n"
            "3. I've heard about flood risk in my area — am I properly covered?\n\n"
            "**Respond naturally as Margaret would, maintaining a warm but concerned tone while expressing genuine "
            "questions about her insurance cover.**\n\n"
            "Directly start with the summary (No 'Context:')\n"
        )

    def _get_fallback_scenario_content(self) -> str:
        """Fallback scenario content when generation fails."""
        return (
            "You are Emily Clarke, a 38-year-old small business owner running a village pub and bed & breakfast "
            "in the Yorkshire Dales. You're calling NFU Mutual to discuss your business insurance renewal and "
            "ask about additional cover for a new outdoor events area you've added.\n\n"
            "BEHAVIORAL GUIDELINES (Act Human):\n"
            "- Be friendly and chatty but focused on getting clear answers\n"
            "- Reference your experience running the business and dealing with seasonal challenges\n"
            '- Show genuine concern about being properly covered for public liability\n\n'
            "YOUR CHARACTER PROFILE:\n"
            "- Took over the family pub 8 years ago, added B&B rooms and now outdoor events\n"
            "- Employs 6 staff including seasonal workers\n"
            "- Values the personal service from her local NFU Mutual agent\n\n"
            "KEY CONCERNS TO RAISE:\n"
            "1. Does my current policy cover the new outdoor marquee and events area?\n"
            "2. I'm hiring temporary staff for summer — is my employer's liability adequate?\n"
            "3. A customer slipped on the patio last month — how would a liability claim work?\n\n"
            "Respond naturally as Emily would, maintaining a warm and practical tone while expressing genuine "
            "concerns about her business insurance cover and customer safety.\n"
        )
