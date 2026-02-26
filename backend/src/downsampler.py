"""LTTB (Largest Triangle Three Buckets) downsampling algorithm."""

from typing import List, Tuple


def lttb_downsample(
    points: List[Tuple[float, float]], target: int
) -> List[Tuple[float, float]]:
    """
    Downsample time-series data using LTTB algorithm.

    Preserves visual characteristics by selecting points that form
    the largest triangles, maintaining peaks, troughs, and trends.

    Args:
        points: List of (timestamp, value) tuples
        target: Target number of points

    Returns:
        Downsampled list of points
    """
    if len(points) <= target:
        return points

    if target <= 2:
        return [points[0], points[-1]]

    # Always include first and last points
    sampled = [points[0]]

    # Bucket size (excluding first and last points)
    bucket_size = (len(points) - 2) / (target - 2)

    point_index = 0  # Start at first point (already sampled)

    for i in range(target - 2):
        # Calculate point average for next bucket
        avg_range_start = int((i + 1) * bucket_size) + 1
        avg_range_end = int((i + 2) * bucket_size) + 1

        if avg_range_end >= len(points):
            avg_range_end = len(points)

        avg_range_length = avg_range_end - avg_range_start

        if avg_range_length > 0:
            avg_x = sum(points[j][0] for j in range(avg_range_start, avg_range_end)) / avg_range_length
            avg_y = sum(points[j][1] for j in range(avg_range_start, avg_range_end)) / avg_range_length
        else:
            avg_x, avg_y = points[avg_range_start]

        # Get the range for current bucket
        range_start = int(i * bucket_size) + 1
        range_end = int((i + 1) * bucket_size) + 1

        # Point in previous bucket
        point_x, point_y = sampled[-1]

        # Find point in current bucket that forms largest triangle
        max_area = -1.0
        max_area_point = range_start

        for j in range(range_start, range_end):
            if j < len(points):
                # Calculate triangle area
                area = abs(
                    (point_x - avg_x) * (points[j][1] - point_y)
                    - (point_x - points[j][0]) * (avg_y - point_y)
                )

                if area > max_area:
                    max_area = area
                    max_area_point = j

        sampled.append(points[max_area_point])
        point_index = max_area_point

    # Always include last point
    sampled.append(points[-1])

    return sampled
