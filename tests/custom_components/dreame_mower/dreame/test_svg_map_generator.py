"""Tests for svg_map_generator module."""

import pytest
from custom_components.dreame_mower.dreame.svg_map_generator import (
    calculate_bounds,
    coord_to_pixel,
    create_svg_document,
    svg_path_from_segments,
    svg_polygon,
    svg_circle,
    svg_dashed_path,
    svg_text_with_background,
    finish_svg_document,
)


class TestCalculateBounds:
    """Test suite for calculate_bounds function."""

    @pytest.mark.parametrize(
        "points,expected",
        [
            # Empty list returns default bounds
            ([], (0, 0, 100, 100)),
            
            # Only sentinel values returns default bounds
            ([[2147483647, 2147483647], [2147483647, 2147483647]], (0, 0, 100, 100)),
            
            # Normal rectangular bounds
            ([[0, 0], [1000, 0], [1000, 800], [0, 800]], (0, 0, 1000, 800)),
            
            # Mixed valid and sentinel values (filters out sentinels)
            ([[100, 200], [2147483647, 2147483647], [300, 400], [500, 600]], (100, 200, 500, 600)),
            
            # Negative coordinates
            ([[-100, -200], [100, 200], [0, 0]], (-100, -200, 100, 200)),
        ],
    )
    def test_calculate_bounds(self, points, expected):
        """Test calculate_bounds with various input scenarios."""
        result = calculate_bounds(points)
        assert result == expected


class TestCoordToPixel:
    """Test suite for coord_to_pixel function."""

    @pytest.mark.parametrize(
        "x,y,bounds,img_width,img_height,padding,expected",
        [
            # Bottom-left corner (Y coordinate is flipped in SVG)
            (0, 0, (0, 0, 1000, 800), 1200, 1000, 50, (50, 930)),
            
            # Top-right corner
            (1000, 800, (0, 0, 1000, 800), 1200, 1000, 50, (1150, 50)),
            
            # Center point (aspect ratio preserved)
            (500, 400, (0, 0, 1000, 800), 1200, 1000, 50, (600, 490)),
            
            # Single point bounds - function adds 100 to create valid dimensions
            (100, 200, (100, 200, 100, 200), 1200, 1000, 50, (50, 950)),
            
            # Negative coordinates with aspect ratio maintained
            (0, 0, (-100, -200, 100, 200), 1200, 1000, 50, (275, 500)),
        ],
    )
    def test_coord_to_pixel(self, x, y, bounds, img_width, img_height, padding, expected):
        """Test coord_to_pixel with various input scenarios."""
        result = coord_to_pixel(x, y, bounds, img_width, img_height, padding)
        assert result == expected


class TestCreateSvgDocument:
    """Test suite for create_svg_document function."""

    @pytest.mark.parametrize(
        "width,height,background_color,expected_lines",
        [
            # Default white background
            (1200, 1000, "white", 3),
            
            # Custom color
            (800, 600, "#add8e6", 3),
            
            # Small dimensions
            (100, 100, "#ffffff", 3),
        ],
    )
    def test_create_svg_document(self, width, height, background_color, expected_lines):
        """Test create_svg_document with various parameters."""
        result = create_svg_document(width, height, background_color)
        assert len(result) == expected_lines
        assert result[0] == '<?xml version="1.0" encoding="UTF-8"?>'
        assert f'width="{width}"' in result[1]
        assert f'height="{height}"' in result[1]
        assert f'fill="{background_color}"' in result[2]


class TestSvgPathFromSegments:
    """Test suite for svg_path_from_segments function."""

    @pytest.mark.parametrize(
        "segments,bounds,img_width,img_height,stroke_color,stroke_width,expected_result",
        [
            # Empty segments returns empty string
            ([], (0, 0, 1000, 800), 1200, 1000, "#ff0000", 2, ""),
            
            # Single segment with two points
            ([[[0, 0], [100, 100]]], (0, 0, 1000, 800), 1200, 1000, "#ff0000", 2, "valid_path"),
            
            # Multiple segments
            ([[[0, 0], [100, 100]], [[200, 200], [300, 300]]], (0, 0, 1000, 800), 1200, 1000, "#00ff00", 3, "valid_path"),
            
            # Segment with single point (too short, skipped but still returns path element with empty data)
            ([[[100, 100]]], (0, 0, 1000, 800), 1200, 1000, "#0000ff", 2, "empty_path"),
        ],
    )
    def test_svg_path_from_segments(self, segments, bounds, img_width, img_height, stroke_color, stroke_width, expected_result):
        """Test svg_path_from_segments with various inputs."""
        result = svg_path_from_segments(segments, bounds, img_width, img_height, stroke_color, stroke_width)
        if expected_result == "":
            assert result == ""
        elif expected_result == "valid_path":
            assert "M " in result and "L " in result
            assert f'stroke="{stroke_color}"' in result
            assert f'stroke-width="{stroke_width}"' in result
        elif expected_result == "empty_path":
            assert '<path d=""' in result
            assert f'stroke="{stroke_color}"' in result


class TestSvgPolygon:
    """Test suite for svg_polygon function."""

    @pytest.mark.parametrize(
        "points,bounds,img_width,img_height,fill_color,stroke_color,expected_tag",
        [
            # Valid triangle
            ([[0, 0], [100, 0], [50, 100]], (0, 0, 1000, 800), 1200, 1000, "#ff0000", "#000000", "polygon"),
            
            # Valid rectangle
            ([[0, 0], [100, 0], [100, 100], [0, 100]], (0, 0, 1000, 800), 1200, 1000, "#00ff00", "#000000", "polygon"),
            
            # Too few points (less than 3) returns empty
            ([[0, 0], [100, 100]], (0, 0, 1000, 800), 1200, 1000, "#0000ff", "#000000", None),
        ],
    )
    def test_svg_polygon(self, points, bounds, img_width, img_height, fill_color, stroke_color, expected_tag):
        """Test svg_polygon with various inputs."""
        result = svg_polygon(points, bounds, img_width, img_height, fill_color, stroke_color)
        if expected_tag is None:
            assert result == ""
        else:
            assert f'<{expected_tag}' in result
            assert f'fill="{fill_color}"' in result
            assert f'stroke="{stroke_color}"' in result


class TestSvgCircle:
    """Test suite for svg_circle function."""

    @pytest.mark.parametrize(
        "x,y,bounds,img_width,img_height,radius,fill_color,stroke_color",
        [
            # Center position
            (500, 400, (0, 0, 1000, 800), 1200, 1000, 10, "#ff0000", "#000000"),
            
            # Corner position
            (0, 0, (0, 0, 1000, 800), 1200, 1000, 5, "#00ff00", "#ffffff"),
            
            # Large radius
            (250, 250, (0, 0, 500, 500), 800, 600, 50, "#0000ff", "#ffff00"),
        ],
    )
    def test_svg_circle(self, x, y, bounds, img_width, img_height, radius, fill_color, stroke_color):
        """Test svg_circle with various inputs."""
        result = svg_circle(x, y, bounds, img_width, img_height, radius, fill_color, stroke_color)
        assert '<circle' in result
        assert f'r="{radius}"' in result
        assert f'fill="{fill_color}"' in result
        assert f'stroke="{stroke_color}"' in result


class TestSvgDashedPath:
    """Test suite for svg_dashed_path function."""

    @pytest.mark.parametrize(
        "points,bounds,img_width,img_height,stroke_color,stroke_width,expected_contains",
        [
            # Valid path with multiple points
            ([[0, 0], [100, 100], [200, 200]], (0, 0, 1000, 800), 1200, 1000, "#ff0000", 3, ["M ", "L ", 'stroke-dasharray="10,5"', 'stroke="#ff0000"']),
            
            # Two points (minimum)
            ([[0, 0], [500, 500]], (0, 0, 1000, 800), 1200, 1000, "#00ff00", 2, ["M ", "L ", 'stroke-dasharray="10,5"']),
            
            # Single point (too short) returns empty
            ([[100, 100]], (0, 0, 1000, 800), 1200, 1000, "#0000ff", 2, None),
        ],
    )
    def test_svg_dashed_path(self, points, bounds, img_width, img_height, stroke_color, stroke_width, expected_contains):
        """Test svg_dashed_path with various inputs."""
        result = svg_dashed_path(points, bounds, img_width, img_height, stroke_color, stroke_width)
        if expected_contains is None:
            assert result == ""
        else:
            for expected_str in expected_contains:
                assert expected_str in result


class TestSvgTextWithBackground:
    """Test suite for svg_text_with_background function."""

    @pytest.mark.parametrize(
        "text,x,y,font_size,text_color,bg_color,expected_elements",
        [
            # Single line text
            ("Hello", 10, 20, 12, "#000000", "#ffffff", ["<g>", "<rect", "<text"]),
            
            # Multi-line text
            ("Line 1\nLine 2\nLine 3", 50, 100, 14, "#ff0000", "#ffff00", ["<g>", "<rect", "<text", "Line 1", "Line 2", "Line 3"]),
            
            # Large font
            ("Big Text", 100, 200, 24, "#0000ff", "#00ff00", ["<g>", "<rect", "<text", "Big Text"]),
        ],
    )
    def test_svg_text_with_background(self, text, x, y, font_size, text_color, bg_color, expected_elements):
        """Test svg_text_with_background with various inputs."""
        result = svg_text_with_background(text, x, y, font_size, text_color, bg_color)
        for element in expected_elements:
            assert element in result
        assert f'fill="{bg_color}"' in result
        assert f'fill="{text_color}"' in result


class TestFinishSvgDocument:
    """Test suite for finish_svg_document function."""

    @pytest.mark.parametrize(
        "svg_lines,expected_ending",
        [
            # Simple document
            (["<svg>", "<rect/>"], "</svg>"),
            
            # Empty document
            ([], "</svg>"),
            
            # Document with multiple elements
            (["<svg>", "<circle/>", "<path/>", "<text/>"], "</svg>"),
        ],
    )
    def test_finish_svg_document(self, svg_lines, expected_ending):
        """Test finish_svg_document with various inputs."""
        result = finish_svg_document(svg_lines)
        assert result.endswith(expected_ending)
        assert "\n" in result or len(svg_lines) <= 1  # Contains newlines or is very short
