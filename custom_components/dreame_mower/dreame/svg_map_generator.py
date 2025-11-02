"""SVG-based map visualization for Dreame Mower Camera Entity.

This module provides SVG generation functions as an alternative to PIL/matplotlib
for better quality and HAOS compatibility.
"""

import logging
from typing import Any, Dict, List, Tuple
from datetime import datetime

_LOGGER = logging.getLogger(__name__)


# Map visualization constants
# NOTE: Rotation (90°, 180°, 270°) currently only works correctly when WIDTH == HEIGHT (square canvas).
# Non-square dimensions will cause the rotated content to be clipped or misaligned because
# the rotated bounding box exceeds the canvas boundaries. Keep these values equal for rotation support.
MAP_IMAGE_WIDTH = 1200
MAP_IMAGE_HEIGHT = 1200
MAP_PADDING = 50

# Color definitions (hex colors for SVG)
COLORS_SVG = {
    'background': '#ffffff',  # white
    'live_background': '#add8e6',  # lightblue
    'map_boundary': '#006400',  # darkgreen
    'mowing_path': '#ffa500',  # orange
    'trajectory': '#1e90ff',  # dodgerblue
    'obstacle': "#ff4d00",  # blue
    'obstacle_fill': "#ff4d0065",  # lightblue
    'live_path': '#32cd32',  # lime
    'live_boundary': '#00008b',  # darkblue
    'start_position': '#00ff00',  # green
    'current_position': '#ff0000',  # red
    'text_color': '#000000',  # black
    'grid_color': '#c8c8c8',  # light gray
    'text_bg': "#ffff003b",  # yellow
}

# Live coordinate scaling factor
LIVE_Y_COORDINATE_SCALE_FACTOR = 16.0


def calculate_bounds(all_points: List[List[int]]) -> Tuple[int, int, int, int]:
    """Calculate the bounding box for all coordinate points.
    
    Returns:
        Tuple of (min_x, min_y, max_x, max_y)
    """
    if not all_points:
        return 0, 0, 100, 100
    
    valid_points = [p for p in all_points if p[0] != 2147483647 and p[1] != 2147483647]
    if not valid_points:
        return 0, 0, 100, 100
    
    min_x = min(p[0] for p in valid_points)
    max_x = max(p[0] for p in valid_points)
    min_y = min(p[1] for p in valid_points)
    max_y = max(p[1] for p in valid_points)
    
    return min_x, min_y, max_x, max_y


def coord_to_pixel(x: int, y: int, bounds: Tuple[int, int, int, int], 
                   img_width: int, img_height: int, padding: int = MAP_PADDING) -> Tuple[int, int]:
    """Convert mower coordinates to image pixel coordinates.
    
    Args:
        x, y: Mower coordinates
        bounds: (min_x, min_y, max_x, max_y) from calculate_bounds
        img_width, img_height: Image dimensions
        padding: Padding around the edges
    
    Returns:
        Tuple of (pixel_x, pixel_y)
    """
    min_x, min_y, max_x, max_y = bounds
    
    # Handle edge case where all coordinates are the same
    if max_x == min_x:
        max_x = min_x + 100
    if max_y == min_y:
        max_y = min_y + 100
    
    # Calculate scale factors
    coord_width = max_x - min_x
    coord_height = max_y - min_y
    available_width = img_width - 2 * padding
    available_height = img_height - 2 * padding
    
    scale_x = available_width / coord_width
    scale_y = available_height / coord_height
    
    # Use the smaller scale to maintain aspect ratio
    scale = min(scale_x, scale_y)
    
    # Convert coordinates
    pixel_x = int(padding + (x - min_x) * scale)
    # Flip Y coordinate (image coordinates have origin at top-left)
    pixel_y = int(padding + (max_y - y) * scale)
    
    return pixel_x, pixel_y


def create_svg_document(width: int, height: int, background_color: str = "white") -> List[str]:
    """Create the basic SVG document structure.
    
    Returns:
        List of SVG lines that can be joined
    """
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="100%" height="100%" fill="{background_color}"/>'
    ]


def svg_path_from_segments(segments: List[List[List[int]]], bounds: Tuple[int, int, int, int], 
                          img_width: int, img_height: int, stroke_color: str, stroke_width: int = 2) -> str:
    """Create SVG path element from path segments."""
    if not segments:
        return ""
    
    path_data = []
    for segment in segments:
        if len(segment) < 2:
            continue
        
        # Convert first point and move to it
        pixel_x, pixel_y = coord_to_pixel(segment[0][0], segment[0][1], bounds, img_width, img_height)
        path_data.append(f"M {pixel_x} {pixel_y}")
        prev_pixel = (pixel_x, pixel_y)
        
        # Draw lines to subsequent points, skipping consecutive duplicates
        for point in segment[1:]:
            pixel_x, pixel_y = coord_to_pixel(point[0], point[1], bounds, img_width, img_height)
            # Only add if this pixel position is different from the previous one
            if (pixel_x, pixel_y) != prev_pixel:
                path_data.append(f"L {pixel_x} {pixel_y}")
                prev_pixel = (pixel_x, pixel_y)
    
    path_str = " ".join(path_data)
    return f'<path d="{path_str}" stroke="{stroke_color}" stroke-width="{stroke_width}" fill="none"/>'


def svg_polygon(points: List[List[int]], bounds: Tuple[int, int, int, int], 
               img_width: int, img_height: int, fill_color: str, stroke_color: str) -> str:
    """Create SVG polygon element."""
    if len(points) < 3:
        return ""
    
    # Convert coordinates to pixels
    pixel_points = []
    for point in points:
        pixel_x, pixel_y = coord_to_pixel(point[0], point[1], bounds, img_width, img_height)
        pixel_points.append(f"{pixel_x},{pixel_y}")
    
    points_str = " ".join(pixel_points)
    return f'<polygon points="{points_str}" fill="{fill_color}" stroke="{stroke_color}"/>'


def svg_circle(x: int, y: int, bounds: Tuple[int, int, int, int], 
              img_width: int, img_height: int, radius: int, fill_color: str, stroke_color: str) -> str:
    """Create SVG circle element."""
    pixel_x, pixel_y = coord_to_pixel(x, y, bounds, img_width, img_height)
    return f'<circle cx="{pixel_x}" cy="{pixel_y}" r="{radius}" fill="{fill_color}" stroke="{stroke_color}"/>'


def svg_dashed_path(points: List[List[int]], bounds: Tuple[int, int, int, int], 
                   img_width: int, img_height: int, stroke_color: str, stroke_width: int = 2) -> str:
    """Create SVG dashed path for trajectories."""
    if len(points) < 2:
        return ""
    
    # Convert first point and move to it
    pixel_x, pixel_y = coord_to_pixel(points[0][0], points[0][1], bounds, img_width, img_height)
    path_data = [f"M {pixel_x} {pixel_y}"]
    
    # Draw lines to subsequent points
    for point in points[1:]:
        pixel_x, pixel_y = coord_to_pixel(point[0], point[1], bounds, img_width, img_height)
        path_data.append(f"L {pixel_x} {pixel_y}")
    
    path_str = " ".join(path_data)
    return f'<path d="{path_str}" stroke="{stroke_color}" stroke-width="{stroke_width}" stroke-dasharray="10,5" fill="none"/>'


def svg_text_with_background(text: str, x: int, y: int, font_size: int = 12, 
                            text_color: str = '#000000', bg_color: str = '#ffffff', 
                            padding: int = 5) -> str:
    """Create SVG text with background rectangle."""
    lines = text.split('\n')
    max_width = max(len(line) for line in lines) * font_size * 0.6
    total_height = len(lines) * (font_size + 2)
    
    rect = f'<rect x="{x - padding}" y="{y - padding}" width="{max_width + 2*padding}" height="{total_height + 2*padding}" fill="{bg_color}" stroke="{text_color}"/>'
    
    text_elements = []
    for i, line in enumerate(lines):
        line_y = y + font_size + i * (font_size + 2)
        text_elements.append(f'<text x="{x}" y="{line_y}" font-family="Arial, sans-serif" font-size="{font_size}" fill="{text_color}">{line}</text>')
    
    return f'<g>{rect}{"".join(text_elements)}</g>'


def finish_svg_document(svg_lines: List[str]) -> str:
    """Close the SVG document and return as string."""
    svg_lines.append('</svg>')
    return '\n'.join(svg_lines)


def generate_svg_live_image(live_coordinates: List[Dict[str, Any]], 
                           base_map_boundary: List[List[int]], 
                           current_map_data: Dict[str, Any] | None,
                           coordinator, rotation: int) -> bytes:
    """Generate live map image in SVG format with current coordinates overlay.
    
    Args:
        live_coordinates: List of live coordinate dictionaries
        base_map_boundary: Base map boundary points
        current_map_data: Current map data dictionary or None
        coordinator: Coordinator instance
        rotation: Rotation angle in degrees (0, 90, 180, or 270) - required
    """
    
    # Create SVG document
    svg_lines = create_svg_document(MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, COLORS_SVG['live_background'])
    
    try:
        # Collect all coordinate points for bounds calculation
        all_points = []
        
        # Add base map boundary points
        if base_map_boundary:
            all_points.extend(base_map_boundary)
        
        # Add live coordinates (with Y scaling)
        if live_coordinates:
            for coord in live_coordinates:
                scaled_y = int(coord['y'] / LIVE_Y_COORDINATE_SCALE_FACTOR)
                all_points.append([coord['x'], scaled_y])
        
        # Add obstacle points
        if current_map_data:
            obstacles = current_map_data.get("obstacle", [])
            for obstacle in obstacles:
                obstacle_data = obstacle.get("data", [])
                all_points.extend(obstacle_data)
        
        if not all_points:
            # No data to display - show message
            svg_lines.append(f'<text x="{MAP_IMAGE_WIDTH // 2}" y="{MAP_IMAGE_HEIGHT // 2}" font-family="Arial, sans-serif" font-size="16" fill="{COLORS_SVG["text_color"]}" text-anchor="middle">No map data available</text>')
        else:
            # Calculate coordinate bounds
            bounds = calculate_bounds(all_points)
            
            # Start rotation group if rotation is specified (only for map content)
            if rotation in [90, 180, 270]:
                center_x = MAP_IMAGE_WIDTH // 2
                center_y = MAP_IMAGE_HEIGHT // 2
                svg_lines.append(f'<g transform="rotate({rotation}, {center_x}, {center_y})">')
            
            # Draw base map boundary if available (reference area)
            if base_map_boundary:
                boundary_segments = [base_map_boundary]  # Single continuous boundary
                boundary_path = svg_path_from_segments(boundary_segments, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                     COLORS_SVG['live_boundary'], 3)
                if boundary_path:
                    svg_lines.append(boundary_path)
            
            # Draw obstacles from base map if available
            if current_map_data:
                obstacles = current_map_data.get("obstacle", [])
                for obstacle in obstacles:
                    obstacle_data = obstacle.get("data", [])
                    if obstacle_data:
                        obstacle_polygon = svg_polygon(obstacle_data, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                      COLORS_SVG['obstacle_fill'], COLORS_SVG['obstacle'])
                        if obstacle_polygon:
                            svg_lines.append(obstacle_polygon)
            
            # Draw live coordinates path
            if len(live_coordinates) > 1:
                # Convert live coordinates with Y scaling
                live_points = []
                for coord in live_coordinates:
                    scaled_y = int(coord['y'] / LIVE_Y_COORDINATE_SCALE_FACTOR)
                    live_points.append([coord['x'], scaled_y])
                
                # Draw the live path
                live_segments = [live_points]  # Single continuous path
                live_path = svg_path_from_segments(live_segments, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                 COLORS_SVG['live_path'], 4)
                if live_path:
                    svg_lines.append(live_path)
                
                # Draw start position
                start_circle = svg_circle(live_points[0][0], live_points[0][1], bounds, 
                                        MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, 6,
                                        COLORS_SVG['start_position'], COLORS_SVG['text_color'])
                svg_lines.append(start_circle)
                
                # Draw current position (last point)
                current_circle = svg_circle(live_points[-1][0], live_points[-1][1], bounds,
                                          MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, 8,
                                          COLORS_SVG['current_position'], '#8b0000')  # darkred outline
                svg_lines.append(current_circle)
                
            elif len(live_coordinates) == 1:
                # Single point - just show current position
                scaled_y = int(live_coordinates[0]['y'] / LIVE_Y_COORDINATE_SCALE_FACTOR)
                current_circle = svg_circle(live_coordinates[0]['x'], scaled_y, bounds,
                                          MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, 8,
                                          COLORS_SVG['current_position'], '#8b0000')
                svg_lines.append(current_circle)
            
            # Close rotation group if it was opened
            if rotation in [90, 180, 270]:
                svg_lines.append('</g>')
        
        # Draw title (outside rotation group)
        title_text = "Dreame Mower - LIVE TRACKING MODE"
        svg_lines.append(f'<text x="{MAP_IMAGE_WIDTH // 2}" y="30" font-family="Arial, sans-serif" font-size="20" font-weight="bold" fill="#8b0000" text-anchor="middle">{title_text}</text>')
        
        # Calculate comprehensive live status info
        total_distance: float = 0.0
        if len(live_coordinates) > 1:
            for i in range(1, len(live_coordinates)):
                prev = live_coordinates[i-1]
                curr = live_coordinates[i]
                dx = curr['x'] - prev['x']
                dy = (curr['y'] - prev['y']) / LIVE_Y_COORDINATE_SCALE_FACTOR
                total_distance += (dx**2 + dy**2) ** 0.5
            total_distance = total_distance / 1000  # Convert to meters
        
        # Get mowing progress if available
        progress_info = ""
        if hasattr(coordinator.device, '_pose_coverage_handler'):
            handler = coordinator.device._pose_coverage_handler
            if handler.progress_percent is not None:
                progress_info = f"Progress: {handler.progress_percent:.1f}%"
            if handler.current_area_sqm is not None:
                progress_info += f" | Area: {handler.current_area_sqm:.1f}m²"
        
        # Add legend in top left
        legend_x = 20
        legend_y = 50
        legend_items = []
        
        # Add legend items based on what's visible in live mode
        if base_map_boundary:
            legend_items.append(("Base Map", COLORS_SVG['live_boundary']))
        if current_map_data and current_map_data.get("obstacle"):
            legend_items.append(("Obstacles", COLORS_SVG['obstacle']))
        if len(live_coordinates) > 1:
            legend_items.append(("Live Path", COLORS_SVG['live_path']))
            legend_items.append(("Start Position", COLORS_SVG['start_position']))
        if live_coordinates:
            legend_items.append(("Current Position", COLORS_SVG['current_position']))
        
        for i, (label, color) in enumerate(legend_items):
            y_pos = legend_y + i * 20
            # Draw color indicator
            svg_lines.append(f'<rect x="{legend_x}" y="{y_pos}" width="15" height="10" fill="{color}"/>')
            # Draw label
            svg_lines.append(f'<text x="{legend_x + 20}" y="{y_pos + 8}" font-family="Arial, sans-serif" font-size="10" fill="{COLORS_SVG["text_color"]}">{label}</text>')
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_lines = [
            "LIVE MOWING SESSION ACTIVE",
            f"Tracking: {len(live_coordinates)} coordinates",
            f"Distance: {total_distance:.1f}m",
            progress_info,
            f"Updated: {timestamp}"
        ]
        
        # Filter out empty lines and create proper multi-line text
        filtered_lines = [line for line in status_lines if line.strip()]
        status_text = "\n".join(filtered_lines)
        status_bg = svg_text_with_background(status_text, 10, MAP_IMAGE_HEIGHT - 80, 10,
                                             COLORS_SVG['text_color'], COLORS_SVG['text_bg'])
        svg_lines.append(status_bg)

    except Exception as ex:
        # Create error message
        _LOGGER.error("Error generating live map SVG: %s", ex, exc_info=True)
        error_text = f"Error generating live map: {str(ex)}"
        svg_lines.append(f'<text x="{MAP_IMAGE_WIDTH // 2}" y="{MAP_IMAGE_HEIGHT // 2}" font-family="Arial, sans-serif" font-size="14" fill="{COLORS_SVG["current_position"]}" text-anchor="middle">{error_text}</text>')

    # Complete SVG document and return as bytes
    svg_content = finish_svg_document(svg_lines)
    result_bytes = svg_content.encode('utf-8')
    return result_bytes


def generate_svg_map_image(data: Dict[str, Any], historical_file_path: str | None, coordinator, rotation: int) -> bytes:
    """Generate map image in SVG format from map data.
    
    Args:
        data: Map data dictionary
        historical_file_path: Path to historical map file or None for current map
        coordinator: Coordinator instance
        rotation: Rotation angle in degrees (0, 90, 180, or 270) - required
    """
    
    # Create SVG document
    svg_lines = create_svg_document(MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, COLORS_SVG['background'])
    
    try:
        # Collect all coordinate points for bounds calculation
        all_points = []
        
        # Plot map data as the main mowing path
        map_items = data.get("map", [])
        segments = []
        track_segments: List[List[List[int]]] = []
        
        if map_items:
            # The map data is a list of dictionaries, each with a 'data' key
            # Process each map item separately to preserve zone boundaries
            for i, item in enumerate(map_items):
                item_data = item.get("data", [])
                item_track = item.get("track", [])
                
                # Add points for bounds calculation
                all_points.extend(item_data)
                all_points.extend(item_track)
                
                # Parse main mowing path from "data" - split by sentinel values within each item
                current_segment: List[List[int]] = []
                for point in item_data:
                    if point[0] == 2147483647 and point[1] == 2147483647:
                        if len(current_segment) > 1:
                            segments.append(current_segment)
                        current_segment = []
                    else:
                        current_segment.append(point)
                if len(current_segment) > 1:
                    segments.append(current_segment)
                
                # Parse additional path from "track" - split by sentinel values within each item
                current_track_segment: List[List[int]] = []
                for point in item_track:
                    if point[0] == 2147483647 and point[1] == 2147483647:
                        if len(current_track_segment) > 1:
                            track_segments.append(current_track_segment)
                        current_track_segment = []
                    else:
                        current_track_segment.append(point)
                if len(current_track_segment) > 1:
                    track_segments.append(current_track_segment)

        # Add obstacle points
        obstacles = data.get("obstacle", [])
        for obstacle in obstacles:
            obstacle_data = obstacle.get("data", [])
            all_points.extend(obstacle_data)

        # Add trajectory points
        trajectories = data.get("trajectory", [])
        for trajectory in trajectories:
            trajectory_data = trajectory.get("data", [])
            all_points.extend(trajectory_data)

        # Add current mower position if available
        mower_position = None
        if hasattr(coordinator.device, 'mower_coordinates') and coordinator.device.mower_coordinates:
            mower_pos = coordinator.device.mower_coordinates
            if mower_pos is not None:
                mower_position = [int(mower_pos[0]), int(mower_pos[1])]
                all_points.append(mower_position)

        if not all_points:
            # No data to display - show message
            svg_lines.append(f'<text x="{MAP_IMAGE_WIDTH // 2}" y="{MAP_IMAGE_HEIGHT // 2}" font-family="Arial, sans-serif" font-size="16" fill="{COLORS_SVG["text_color"]}" text-anchor="middle">No map data available</text>')
        else:
            # Calculate coordinate bounds
            bounds = calculate_bounds(all_points)
            
            # Start rotation group if rotation is specified (only for map content)
            if rotation in [90, 180, 270]:
                center_x = MAP_IMAGE_WIDTH // 2
                center_y = MAP_IMAGE_HEIGHT // 2
                svg_lines.append(f'<g transform="rotate({rotation}, {center_x}, {center_y})">')
            
            # Draw main mowing path segments (map boundary)
            if segments:
                boundary_path = svg_path_from_segments(segments, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                     COLORS_SVG['map_boundary'], 2)
                if boundary_path:
                    svg_lines.append(boundary_path)

            # Draw additional path from "track" (mowing path)
            if track_segments:
                track_path = svg_path_from_segments(track_segments, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                  COLORS_SVG['mowing_path'], 2)
                if track_path:
                    svg_lines.append(track_path)

            # Draw obstacles
            for obstacle in obstacles:
                obstacle_data = obstacle.get("data", [])
                if obstacle_data:
                    obstacle_polygon = svg_polygon(obstacle_data, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                 COLORS_SVG['obstacle_fill'], COLORS_SVG['obstacle'])
                    if obstacle_polygon:
                        svg_lines.append(obstacle_polygon)

            # Draw trajectory (outer path) - using dashed line
            for trajectory in trajectories:
                trajectory_data = trajectory.get("data", [])
                if trajectory_data:
                    trajectory_path = svg_dashed_path(trajectory_data, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                    COLORS_SVG['trajectory'], 3)
                    if trajectory_path:
                        svg_lines.append(trajectory_path)

            # Draw current mower position
            if mower_position:
                mower_circle = svg_circle(mower_position[0], mower_position[1], bounds,
                                        MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, 6,
                                        COLORS_SVG['current_position'], COLORS_SVG['text_color'])
                svg_lines.append(mower_circle)
            
            # Close rotation group if it was opened
            if rotation in [90, 180, 270]:
                svg_lines.append('</g>')
        
        # Draw title (outside rotation group)
        import os
        if historical_file_path:
            title = f"Dreame Mower Map (Historical: {os.path.basename(historical_file_path)})"
        else:
            title = "Dreame Mower Map (Current)"
        
        svg_lines.append(f'<text x="{MAP_IMAGE_WIDTH // 2}" y="30" font-family="Arial, sans-serif" font-size="16" font-weight="bold" fill="{COLORS_SVG["text_color"]}" text-anchor="middle">{title}</text>')
        
        # Add legend in top left
        legend_x = 20
        legend_y = 50
        legend_items = []
        
        if segments:
            legend_items.append(("Map Boundary", COLORS_SVG['map_boundary']))
        if track_segments:
            legend_items.append(("Mowing Path", COLORS_SVG['mowing_path']))
        if obstacles:
            legend_items.append(("Obstacles", COLORS_SVG['obstacle']))
        if trajectories:
            legend_items.append(("Trajectory", COLORS_SVG['trajectory']))
        if mower_position:
            legend_items.append(("Mower Position", COLORS_SVG['current_position']))
        
        for i, (label, color) in enumerate(legend_items):
            y_pos = legend_y + i * 20
            # Draw color indicator
            svg_lines.append(f'<rect x="{legend_x}" y="{y_pos}" width="15" height="10" fill="{color}"/>')
            # Draw label
            svg_lines.append(f'<text x="{legend_x + 20}" y="{y_pos + 8}" font-family="Arial, sans-serif" font-size="10" fill="{COLORS_SVG["text_color"]}">{label}</text>')
        
        # Add timestamp from map data (use 'start' timestamp if available)
        start_timestamp = data.get("start")
        if start_timestamp:
            # Use UTC to ensure consistent timestamps across different timezones
            from datetime import timezone
            timestamp = datetime.fromtimestamp(start_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            timestamp_text = f"Started: {timestamp}"
        else:
            timestamp_text = "No time information"
        timestamp_bg = svg_text_with_background(timestamp_text, 10, MAP_IMAGE_HEIGHT - 25, 10,
                                              COLORS_SVG['text_color'], COLORS_SVG['background'], 3)
        svg_lines.append(timestamp_bg)

    except Exception as ex:
        # Create error message
        _LOGGER.error("Error generating map SVG: %s", ex, exc_info=True)
        error_text = f"Error generating map: {str(ex)}"
        svg_lines.append(f'<text x="{MAP_IMAGE_WIDTH // 2}" y="{MAP_IMAGE_HEIGHT // 2}" font-family="Arial, sans-serif" font-size="14" fill="{COLORS_SVG["current_position"]}" text-anchor="middle">{error_text}</text>')

    # Complete SVG document and return as bytes
    svg_content = finish_svg_document(svg_lines)
    result_bytes = svg_content.encode('utf-8')
    return result_bytes