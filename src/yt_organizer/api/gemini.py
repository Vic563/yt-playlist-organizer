"""Gemini API client for AI-powered topic classification."""

import json
import re
from typing import Optional

import google.generativeai as genai

from yt_organizer.core.config import Settings
from yt_organizer.core.constants import GEMINI_MODEL, GEMINI_DEFAULT_TEMPERATURE
from yt_organizer.core.exceptions import ClassificationError, ConfigurationError
from yt_organizer.core.logging import get_logger
from yt_organizer.core.models import ClassificationResult, TopicSource, Video

logger = get_logger("gemini")


class GeminiClient:
    """Client for interacting with Gemini API."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize Gemini client.
        
        Args:
            settings: Application settings
        
        Raises:
            ConfigurationError: If Gemini API key is not configured
        """
        self.settings = settings or Settings()
        
        if not self.settings.gemini_api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY is not set. "
                "Get your API key from https://makersuite.google.com/app/apikey"
            )
        
        genai.configure(api_key=self.settings.gemini_api_key)
        self.model = genai.GenerativeModel(GEMINI_MODEL)
        logger.info(f"Initialized Gemini client with model: {GEMINI_MODEL}")
    
    def classify_video_topic(
        self,
        video: Video,
        source: TopicSource = TopicSource.BOTH,
        temperature: float = GEMINI_DEFAULT_TEMPERATURE
    ) -> ClassificationResult:
        """
        Classify a video into a topic using AI.
        
        Args:
            video: Video to classify
            source: What to use for classification (title, description, or both)
            temperature: Model temperature (0.0 to 1.0)
        
        Returns:
            Classification result with topic
        
        Raises:
            ClassificationError: If classification fails
        """
        # Build input text based on source
        input_parts = []
        
        if source in (TopicSource.TITLE, TopicSource.BOTH):
            input_parts.append(f"Title: {video.title}")
        
        if source in (TopicSource.DESCRIPTION, TopicSource.BOTH):
            if video.description:
                # Limit description length to avoid token limits
                desc = video.description[:500]
                if len(video.description) > 500:
                    desc += "..."
                input_parts.append(f"Description: {desc}")
        
        if not input_parts:
            raise ClassificationError("No content available for classification")
        
        input_text = "\n".join(input_parts)
        
        # Create prompt
        prompt = self._create_classification_prompt(input_text)
        
        try:
            # Generate response
            generation_config = genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=100,
            )
            
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Parse response
            topic = self._parse_topic_response(response.text)
            
            return ClassificationResult(
                video_id=video.id,
                video_title=video.title,
                topic=topic,
                source=source,
            )
            
        except Exception as e:
            logger.error(f"Classification failed for video {video.id}: {e}")
            raise ClassificationError(f"Failed to classify video: {e}")
    
    def _create_classification_prompt(self, input_text: str) -> str:
        """
        Create the classification prompt.
        
        Args:
            input_text: Video information to classify
        
        Returns:
            Formatted prompt
        """
        return f"""You are labeling YouTube videos into concise topic playlists.
Your task is to analyze the video information and suggest a SHORT, clear topic label
that would work well as a playlist title.

Guidelines:
- Keep topics SHORT (2-4 words maximum)
- Use general categories that multiple videos could fit into
- Be consistent with naming (e.g., always "Python Tutorials" not "Python Tutorial")
- Avoid special characters, emojis, or dates
- Focus on the main subject matter

Good examples:
- "Python Tutorials"
- "Cooking Recipes"
- "Tech Reviews"
- "Fitness Workouts"
- "Music Production"
- "Travel Vlogs"
- "Gaming Content"

Bad examples:
- "Interesting Videos About Various Topics" (too long)
- "Python 🐍" (has emoji)
- "Videos from 2024" (has date)
- "Misc" (too vague)

Video Information:
{input_text}

Respond ONLY with a JSON object in this exact format:
{{"topic": "Your Topic Here"}}"""
    
    def _parse_topic_response(self, response_text: str) -> str:
        """
        Parse the topic from Gemini's response.
        
        Args:
            response_text: Raw response from Gemini
        
        Returns:
            Extracted topic
        """
        if not response_text:
            logger.warning("Empty response from Gemini")
            return "Uncategorized"
        
        # Try to extract JSON
        json_match = re.search(r'\{[^}]*"topic"[^}]*\}', response_text)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                topic = data.get("topic", "").strip()
                if topic:
                    # Clean and validate topic
                    topic = self._clean_topic(topic)
                    return topic
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON from response: {response_text}")
        
        # Fallback: try to extract first line
        lines = response_text.strip().split('\n')
        if lines:
            topic = self._clean_topic(lines[0])
            if topic:
                return topic
        
        logger.warning(f"Could not parse topic from response: {response_text}")
        return "Uncategorized"
    
    def _clean_topic(self, topic: str) -> str:
        """
        Clean and normalize a topic string.
        
        Args:
            topic: Raw topic string
        
        Returns:
            Cleaned topic
        """
        # Remove quotes, extra whitespace
        topic = topic.strip().strip('"\'')
        
        # Remove emojis and special characters
        topic = re.sub(r'[^\w\s-]', '', topic)
        
        # Normalize whitespace
        topic = re.sub(r'\s+', ' ', topic)
        
        # Limit length
        if len(topic) > 60:
            topic = topic[:57] + "..."
        
        return topic or "Uncategorized"
    
    def batch_classify_videos(
        self,
        videos: list[Video],
        source: TopicSource = TopicSource.BOTH,
        temperature: float = GEMINI_DEFAULT_TEMPERATURE
    ) -> list[ClassificationResult]:
        """
        Classify multiple videos in batch.
        
        Args:
            videos: List of videos to classify
            source: What to use for classification
            temperature: Model temperature
        
        Returns:
            List of classification results
        """
        results = []
        
        for video in videos:
            try:
                result = self.classify_video_topic(video, source, temperature)
                results.append(result)
                logger.debug(f"Classified '{video.title}' as '{result.topic}'")
            except ClassificationError as e:
                logger.warning(f"Failed to classify video {video.id}: {e}")
                # Create a fallback result
                results.append(ClassificationResult(
                    video_id=video.id,
                    video_title=video.title,
                    topic="Uncategorized",
                    confidence=0.0,
                    source=source,
                ))
        
        return results
    
    def test_connection(self) -> bool:
        """
        Test if Gemini API connection is working.
        
        Returns:
            True if connection is successful
        """
        try:
            response = self.model.generate_content("Say 'Hello'")
            logger.info("Gemini API connection test successful")
            return bool(response.text)
        except Exception as e:
            logger.error(f"Gemini API connection test failed: {e}")
            return False
