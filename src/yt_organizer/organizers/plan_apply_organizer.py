"""Plan-and-apply organizer with dry-run support and operation deduplication."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
import time

from yt_organizer.api.youtube_optimized import OptimizedYouTubeClient
from yt_organizer.core.config import Settings
from yt_organizer.core.logging import get_logger
from yt_organizer.core.models import Video, Playlist, PrivacyStatus, TopicSource
from yt_organizer.core.performance import StateManager
from yt_organizer.organizers.classifier_optimized import OptimizedClassifier

logger = get_logger("plan_apply_organizer")


@dataclass
class PlaylistOperation:
    """Represents a single playlist operation."""
    operation_type: str  # "create", "add_video", "remove_video"
    playlist_id: Optional[str] = None
    playlist_title: Optional[str] = None
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    privacy: PrivacyStatus = PrivacyStatus.PRIVATE
    
    def __hash__(self):
        return hash((self.operation_type, self.playlist_id, self.video_id))
    
    def __eq__(self, other):
        return (self.operation_type == other.operation_type and 
                self.playlist_id == other.playlist_id and
                self.video_id == other.video_id)


@dataclass 
class ExecutionPlan:
    """Complete execution plan with operations and metadata."""
    operations: List[PlaylistOperation]
    total_videos: int
    total_playlists: int
    estimated_api_calls: int
    estimated_duration: float
    
    def get_summary(self) -> Dict:
        """Get plan summary."""
        op_counts = defaultdict(int)
        playlists_to_create = set()
        videos_to_add = set()
        
        for op in self.operations:
            op_counts[op.operation_type] += 1
            if op.operation_type == "create":
                playlists_to_create.add(op.playlist_title)
            elif op.operation_type == "add_video":
                videos_to_add.add(op.video_id)
        
        return {
            "total_operations": len(self.operations),
            "operation_types": dict(op_counts),
            "playlists_to_create": len(playlists_to_create),
            "unique_videos_to_add": len(videos_to_add),
            "estimated_api_calls": self.estimated_api_calls,
            "estimated_duration_seconds": self.estimated_duration
        }


class PlanAndApplyOrganizer:
    """Organizer that separates planning from execution with performance optimizations."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize organizer.
        
        Args:
            settings: Application settings
        """
        self.settings = settings or Settings()
        self.youtube_client = OptimizedYouTubeClient(settings=self.settings)
        self.classifier = OptimizedClassifier(settings=self.settings)
        self.state_manager = StateManager(
            self.settings.cache_dir,
            enabled=self.settings.enable_state
        )
    
    def create_execution_plan(
        self,
        source_playlist_id: str,
        limit: Optional[int] = None,
        topic_source: TopicSource = TopicSource.BOTH,
        privacy: PrivacyStatus = PrivacyStatus.PRIVATE,
        skip_processed: bool = True
    ) -> ExecutionPlan:
        """
        Create execution plan without making any changes.
        
        Args:
            source_playlist_id: Source playlist (e.g., Watch Later) 
            limit: Maximum videos to process
            topic_source: Classification source
            privacy: Privacy for created playlists
            skip_processed: Skip videos already processed
            
        Returns:
            ExecutionPlan with all operations
        """
        logger.info(f"Creating execution plan for playlist {source_playlist_id}")
        start_time = time.time()
        
        # Step 1: Fetch videos from source playlist
        videos = []
        for video in self.youtube_client.list_playlist_videos_optimized(
            source_playlist_id, limit=limit
        ):
            if skip_processed and self.state_manager.is_processed(source_playlist_id, video.id):
                logger.debug(f"Skipping already processed video: {video.id}")
                continue
            videos.append(video)
        
        if not videos:
            logger.info("No videos to process")
            return ExecutionPlan([], 0, 0, 0, 0.0)
        
        logger.info(f"Found {len(videos)} videos to process")
        
        # Step 2: Get detailed video information in batches
        video_ids = [v.id for v in videos if v.id]
        detailed_videos = self.youtube_client.get_video_details_batch(video_ids)
        
        # Create video lookup
        video_lookup = {v.id: v for v in detailed_videos}
        
        # Step 3: Classify videos
        logger.info("Classifying videos...")
        topic_to_videos = self.classifier.classify_videos_batch(detailed_videos, topic_source)
        
        # Step 4: Build execution plan
        operations = []
        existing_playlists = self._get_existing_playlists()
        playlists_to_create = set()
        
        for topic, topic_videos in topic_to_videos.items():
            if not topic_videos:
                continue
                
            # Find or plan to create playlist
            playlist_id = self._find_playlist_for_topic(topic, existing_playlists)
            
            if not playlist_id:
                # Plan to create playlist
                playlist_title = self._generate_playlist_title(topic)
                playlists_to_create.add(playlist_title)
                
                operations.append(PlaylistOperation(
                    operation_type="create",
                    playlist_title=playlist_title,
                    privacy=privacy
                ))
                
                # Use placeholder ID for subsequent operations
                playlist_id = f"new_{playlist_title}"
            
            # Plan to add videos
            for video in topic_videos:
                operations.append(PlaylistOperation(
                    operation_type="add_video",
                    playlist_id=playlist_id,
                    video_id=video.id,
                    video_title=video.title
                ))
        
        # Deduplicate operations
        operations = list(set(operations))
        
        # Estimate API calls and duration
        estimated_calls = self._estimate_api_calls(operations)
        estimated_duration = self._estimate_duration(operations)
        
        plan_time = time.time() - start_time
        logger.info(f"Created execution plan in {plan_time:.1f}s: {len(operations)} operations")
        
        return ExecutionPlan(
            operations=operations,
            total_videos=len(videos),
            total_playlists=len(playlists_to_create),
            estimated_api_calls=estimated_calls,
            estimated_duration=estimated_duration
        )
    
    def execute_plan(
        self,
        plan: ExecutionPlan,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Execute the plan.
        
        Args:
            plan: Execution plan to execute
            dry_run: If True, only log what would be done
            
        Returns:
            Execution results
        """
        if dry_run:
            return self._dry_run_plan(plan)
        
        logger.info(f"Executing plan with {len(plan.operations)} operations")
        start_time = time.time()
        
        results = {
            "playlists_created": 0,
            "videos_added": 0,
            "errors": [],
            "playlist_mapping": {}  # Maps placeholder IDs to real IDs
        }
        
        # Group operations by type
        create_ops = [op for op in plan.operations if op.operation_type == "create"]
        add_ops = [op for op in plan.operations if op.operation_type == "add_video"]
        
        # Execute playlist creation first
        for op in create_ops:
            try:
                playlist = self.youtube_client.create_playlist(
                    title=op.playlist_title,
                    privacy=op.privacy
                )
                placeholder_id = f"new_{op.playlist_title}"
                results["playlist_mapping"][placeholder_id] = playlist.id
                results["playlists_created"] += 1
                logger.info(f"Created playlist: {op.playlist_title} -> {playlist.id}")
                
            except Exception as e:
                error_msg = f"Failed to create playlist {op.playlist_title}: {e}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
        
        # Update add operations with real playlist IDs
        for op in add_ops:
            if op.playlist_id in results["playlist_mapping"]:
                op.playlist_id = results["playlist_mapping"][op.playlist_id]
        
        # Group add operations by playlist for batch processing
        playlist_operations = defaultdict(list)
        for op in add_ops:
            if op.playlist_id and not op.playlist_id.startswith("new_"):
                playlist_operations[op.playlist_id].append(op.video_id)
        
        # Execute batch add operations
        if playlist_operations:
            operations_list = []
            for playlist_id, video_ids in playlist_operations.items():
                for video_id in video_ids:
                    operations_list.append((playlist_id, video_id))
            
            batch_results = self.youtube_client.batch_add_videos_to_playlists(operations_list)
            for playlist_id, added_count in batch_results.items():
                results["videos_added"] += added_count
        
        # Update state for processed videos
        source_playlist_id = None  # Would need to pass this in
        if source_playlist_id:
            for op in add_ops:
                if op.video_id:
                    self.state_manager.mark_processed(source_playlist_id, op.video_id)
        
        execution_time = time.time() - start_time
        results["execution_time"] = execution_time
        
        logger.info(f"Plan executed in {execution_time:.1f}s: "
                   f"{results['playlists_created']} playlists created, "
                   f"{results['videos_added']} videos added")
        
        return results
    
    def organize_videos(
        self,
        source_playlist_id: str,
        limit: Optional[int] = None,
        topic_source: TopicSource = TopicSource.BOTH,
        privacy: PrivacyStatus = PrivacyStatus.PRIVATE,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Complete organize workflow: plan then execute.
        
        Args:
            source_playlist_id: Source playlist ID
            limit: Maximum videos to process
            topic_source: Classification source  
            privacy: Privacy for created playlists
            dry_run: Only show what would be done
            
        Returns:
            Combined results
        """
        # Create plan
        plan = self.create_execution_plan(
            source_playlist_id=source_playlist_id,
            limit=limit,
            topic_source=topic_source,
            privacy=privacy
        )
        
        # Execute plan  
        results = self.execute_plan(plan, dry_run=dry_run)
        results["plan"] = plan.get_summary()
        
        return results
    
    def _dry_run_plan(self, plan: ExecutionPlan) -> Dict[str, any]:
        """Execute plan in dry-run mode."""
        logger.info("=== DRY RUN MODE ===")
        
        summary = plan.get_summary()
        
        logger.info(f"Would execute {summary['total_operations']} operations:")
        for op_type, count in summary['operation_types'].items():
            logger.info(f"  - {op_type}: {count}")
        
        logger.info(f"Would create {summary['playlists_to_create']} new playlists")
        logger.info(f"Would add {summary['unique_videos_to_add']} unique videos")
        logger.info(f"Estimated API calls: {plan.estimated_api_calls}")
        logger.info(f"Estimated duration: {plan.estimated_duration:.1f}s")
        
        # Show performance metrics
        self.youtube_client.log_performance_summary()
        classifier_stats = self.classifier.get_classification_stats()
        if classifier_stats["cache"]["enabled"]:
            logger.info(f"Classification cache: {classifier_stats['cache']['total_entries']} entries")
        
        return {
            "dry_run": True,
            "plan": summary,
            "performance_metrics": self.youtube_client.get_performance_metrics()
        }
    
    def _get_existing_playlists(self) -> Dict[str, str]:
        """Get mapping of playlist titles to IDs."""
        playlists = {}
        try:
            for playlist in self.youtube_client.list_playlists():
                playlists[playlist.title.lower()] = playlist.id
        except Exception as e:
            logger.warning(f"Failed to fetch existing playlists: {e}")
        return playlists
    
    def _find_playlist_for_topic(self, topic: str, existing_playlists: Dict[str, str]) -> Optional[str]:
        """Find existing playlist for topic."""
        # Try exact match first
        if topic.lower() in existing_playlists:
            return existing_playlists[topic.lower()]
        
        # Try variations
        variations = [
            f"{topic} Videos",
            f"{topic} Playlist", 
            f"{topic}s",
            topic.replace(" ", "")
        ]
        
        for variation in variations:
            if variation.lower() in existing_playlists:
                return existing_playlists[variation.lower()]
        
        return None
    
    def _generate_playlist_title(self, topic: str) -> str:
        """Generate playlist title for topic."""
        # Clean up topic and ensure it's a good playlist title
        title = topic.strip()
        if len(title) > 50:  # YouTube title limits
            title = title[:47] + "..."
        return title
    
    def _estimate_api_calls(self, operations: List[PlaylistOperation]) -> int:
        """Estimate API calls needed for operations."""
        calls = 0
        
        # Playlist creations: 1 call each
        calls += len([op for op in operations if op.operation_type == "create"])
        
        # Video additions: batched by playlist, ~1 call per video (conservative)
        calls += len([op for op in operations if op.operation_type == "add_video"])
        
        # Add overhead for prefetch operations
        playlists = set(op.playlist_id for op in operations if op.playlist_id)
        calls += len(playlists)  # Membership prefetch
        
        return calls
    
    def _estimate_duration(self, operations: List[PlaylistOperation]) -> float:
        """Estimate execution duration."""
        # Base estimates per operation type
        create_time = 2.0  # seconds per playlist creation
        add_time = 0.5     # seconds per video add (with batching)
        
        creates = len([op for op in operations if op.operation_type == "create"])
        adds = len([op for op in operations if op.operation_type == "add_video"])
        
        base_time = creates * create_time + adds * add_time
        
        # Add overhead for rate limiting and backoff
        overhead = base_time * 0.2  # 20% overhead
        
        return base_time + overhead
    
    def cleanup(self):
        """Clean up resources."""
        self.youtube_client.cleanup()
        self.classifier.cleanup()