"""Optimized video classifier with caching and heuristics."""

import re
from typing import Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor
import hashlib

from yt_organizer.api.gemini import GeminiClient
from yt_organizer.core.config import Settings
from yt_organizer.core.constants import GEMINI_MODEL
from yt_organizer.core.logging import get_logger
from yt_organizer.core.models import Video, ClassificationResult, TopicSource
from yt_organizer.core.performance import ClassificationCache, PerformanceMetrics

logger = get_logger("classifier_optimized")


class KeywordHeuristics:
    """Heuristic keyword-based classification to skip LLM calls."""
    
    def __init__(self):
        # Define topic keywords (expandable)
        self.topic_keywords = {
            "Programming": [
                "python", "javascript", "java", "c++", "coding", "programming",
                "software", "developer", "code", "tutorial", "algorithm",
                "data structures", "web development", "frontend", "backend"
            ],
            "Machine Learning": [
                "machine learning", "ml", "ai", "artificial intelligence",
                "neural network", "deep learning", "tensorflow", "pytorch",
                "data science", "nlp", "computer vision"
            ],
            "Tech Reviews": [
                "review", "unboxing", "tech review", "phone review",
                "laptop review", "gadget", "technology", "specs"
            ],
            "Music": [
                "music", "song", "album", "artist", "band", "concert",
                "guitar", "piano", "drums", "vocals", "lyrics"
            ],
            "Gaming": [
                "gaming", "gameplay", "game", "streamer", "esports",
                "nintendo", "playstation", "xbox", "pc gaming"
            ],
            "Cooking": [
                "recipe", "cooking", "food", "chef", "kitchen",
                "baking", "meal", "ingredients", "restaurant"
            ],
            "Fitness": [
                "workout", "fitness", "gym", "exercise", "training",
                "muscle", "cardio", "strength", "health"
            ],
            "Travel": [
                "travel", "trip", "vacation", "destination", "adventure",
                "hotel", "flight", "tourism", "explore"
            ]
        }
        
        # Compile regex patterns for efficiency
        self.topic_patterns = {}
        for topic, keywords in self.topic_keywords.items():
            pattern = r'\b(?:' + '|'.join(re.escape(kw) for kw in keywords) + r')\b'
            self.topic_patterns[topic] = re.compile(pattern, re.IGNORECASE)
    
    def classify_by_keywords(self, title: str, description: str = "") -> Optional[str]:
        """
        Attempt to classify video using keyword heuristics.
        
        Args:
            title: Video title
            description: Video description
            
        Returns:
            Topic name if confident match found, None otherwise
        """
        text = f"{title} {description}".lower()
        
        topic_scores = {}
        for topic, pattern in self.topic_patterns.items():
            matches = len(pattern.findall(text))
            if matches > 0:
                topic_scores[topic] = matches
        
        if topic_scores:
            # Return topic with highest score
            best_topic = max(topic_scores.items(), key=lambda x: x[1])
            # Only return if we have a strong signal (multiple matches or title match)
            if best_topic[1] > 1 or any(kw in title.lower() for kw in self.topic_keywords[best_topic[0]]):
                logger.debug(f"Heuristic classification: '{title}' -> {best_topic[0]} (score: {best_topic[1]})")
                return best_topic[0]
        
        return None
    
    def add_custom_keywords(self, topic: str, keywords: List[str]):
        """Add custom keywords for a topic."""
        if topic not in self.topic_keywords:
            self.topic_keywords[topic] = []
        self.topic_keywords[topic].extend(keywords)
        
        # Recompile pattern
        pattern = r'\b(?:' + '|'.join(re.escape(kw) for kw in self.topic_keywords[topic]) + r')\b'
        self.topic_patterns[topic] = re.compile(pattern, re.IGNORECASE)


class OptimizedClassifier:
    """Optimized video classifier with caching, heuristics, and concurrency."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize optimized classifier.
        
        Args:
            settings: Application settings
        """
        self.settings = settings or Settings()
        self.gemini_client = None
        self.heuristics = KeywordHeuristics()
        self.cache = ClassificationCache(
            self.settings.cache_dir,
            enabled=self.settings.enable_cache
        )
        self.metrics = PerformanceMetrics()
        self.executor = ThreadPoolExecutor(max_workers=self.settings.llm_concurrency)
        
        # Cache key components
        self.model_name = "gemini-2.5-flash"  # Use fast model by default
        self.prompt_version = "v1.0"  # Version for cache invalidation
    
    @property
    def _gemini_client(self) -> Optional[GeminiClient]:
        """Lazy load Gemini client."""
        if self.gemini_client is None and self.settings.gemini_api_key:
            try:
                self.gemini_client = GeminiClient(settings=self.settings)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
        return self.gemini_client
    
    def _get_cache_key_components(self, video: Video, source: TopicSource) -> Tuple[str, str, str]:
        """Get cache key components for a video classification."""
        # Create content hash for prompt version  
        content = f"{video.title}:{video.description}:{source.value}"
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        prompt_version = f"{self.prompt_version}:{content_hash}"
        
        return video.id, self.model_name, prompt_version
    
    def classify_video_optimized(
        self,
        video: Video,
        source: TopicSource = TopicSource.BOTH
    ) -> Optional[ClassificationResult]:
        """
        Classify video with optimizations: heuristics first, then cached LLM, then fresh LLM.
        
        Args:
            video: Video to classify
            source: Classification source (title, description, or both)
            
        Returns:
            ClassificationResult or None if classification fails
        """
        try:
            # Step 1: Try heuristic classification first
            title = video.title or ""
            description = video.description or "" if source in (TopicSource.DESCRIPTION, TopicSource.BOTH) else ""
            
            heuristic_topic = self.heuristics.classify_by_keywords(title, description)
            if heuristic_topic:
                self.metrics.record_cache_hit()  # Treat heuristic as cache hit
                return ClassificationResult(
                    video_id=video.id,
                    video_title=title,
                    topic=heuristic_topic,
                    source=source,
                    confidence=0.9  # High confidence for keyword matches
                )
            
            # Step 2: Check classification cache
            cache_key = self._get_cache_key_components(video, source)
            cached_result = self.cache.get(*cache_key)
            if cached_result:
                self.metrics.record_cache_hit()
                logger.debug(f"Cache hit for video {video.id}: {cached_result['topic']}")
                return ClassificationResult(
                    video_id=video.id,
                    video_title=title,
                    topic=cached_result["topic"],
                    source=source,
                    confidence=cached_result["confidence"]
                )
            
            # Step 3: Use LLM classification
            self.metrics.record_cache_miss()
            if self._gemini_client:
                # Use optimized settings for speed
                result = self._gemini_client.classify_video_topic(
                    video=video,
                    source=source,
                    temperature=0.0  # Deterministic for consistency
                )
                
                if result and result.topic:
                    # Cache the result
                    self.cache.put(
                        cache_key[0], cache_key[1], cache_key[2],
                        result.topic, getattr(result, 'confidence', 1.0)
                    )
                    logger.debug(f"LLM classification for video {video.id}: {result.topic}")
                    return result
            
            logger.warning(f"Failed to classify video {video.id}: {title}")
            return None
            
        except Exception as e:
            logger.error(f"Error classifying video {video.id}: {e}")
            return None
    
    def classify_videos_batch(
        self,
        videos: List[Video],
        source: TopicSource = TopicSource.BOTH
    ) -> Dict[str, List[Video]]:
        """
        Classify multiple videos concurrently with optimizations.
        
        Args:
            videos: List of videos to classify
            source: Classification source
            
        Returns:
            Dictionary mapping topics to videos
        """
        from collections import defaultdict
        topic_map = defaultdict(list)
        
        if not videos:
            return dict(topic_map)
        
        # Submit classification tasks to thread pool
        future_to_video = {}
        for video in videos:
            future = self.executor.submit(self.classify_video_optimized, video, source)
            future_to_video[future] = video
        
        # Collect results as they complete
        classified_count = 0
        for future in future_to_video:
            video = future_to_video[future]
            try:
                result = future.result(timeout=60)  # 1 minute timeout per video
                if result and result.topic:
                    topic_map[result.topic].append(video)
                    classified_count += 1
                else:
                    # Fallback to "Misc" for unclassified videos
                    topic_map["Misc"].append(video)
                    
                self.metrics.record_video_processed()
                
            except Exception as e:
                logger.warning(f"Failed to classify video {video.id}: {e}")
                topic_map["Misc"].append(video)
        
        logger.info(f"Classified {classified_count}/{len(videos)} videos into {len(topic_map)} topics")
        return dict(topic_map)
    
    def get_classification_stats(self) -> Dict:
        """Get classification statistics."""
        cache_stats = self.cache.get_stats()
        metrics = self.metrics.get_summary()
        
        return {
            "cache": cache_stats,
            "performance": metrics,
            "heuristics": {
                "available_topics": list(self.heuristics.topic_keywords.keys())
            }
        }
    
    def add_topic_keywords(self, topic: str, keywords: List[str]):
        """Add custom keywords for a topic."""
        self.heuristics.add_custom_keywords(topic, keywords)
        logger.info(f"Added {len(keywords)} keywords for topic '{topic}'")
    
    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)