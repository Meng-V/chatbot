"""Library Location Service - Database access for campus/library/space hierarchy.

This service replaces hardcoded .env variables with database queries for:
- Campus locations (Oxford, Hamilton, Middletown)
- Library buildings (King, Art & Architecture, Rentschler, Gardner-Harvey)
- Library spaces (Maker Space, Special Collections, etc.)
"""
from typing import Optional, Dict, List, Tuple
from src.database.prisma_client import get_prisma_client


class LocationService:
    """Service for querying library location hierarchy."""
    
    def __init__(self):
        self._client = get_prisma_client()
        self._cache: Dict[str, any] = {}
    
    async def get_building_id(self, building_name: str) -> Optional[str]:
        """Get LibCal building ID by library name or short name.
        
        This returns the ID used for ROOM RESERVATIONS API (Image 2).
        For hours checking, use get_location_id() instead.
        
        Handles campus-based references:
        - "hamilton" or "hamilton library" → Rentschler Library
        - "middletown" or "middletown library" → Gardner-Harvey Library
        
        Args:
            building_name: Library name (e.g., "king", "art", "rentschler", "hamilton", "middletown")
        
        Returns:
            LibCal building ID for reservations (e.g., "2047") or None if not found
        """
        building_lower = building_name.lower().strip()
        
        # Check cache first
        cache_key = f"building_id:{building_lower}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Search by short name or name
        library = await self._client.library.find_first(
            where={
                "OR": [
                    {"shortName": {"equals": building_lower, "mode": "insensitive"}},
                    {"name": {"contains": building_lower, "mode": "insensitive"}}
                ]
            }
        )
        
        if library:
            self._cache[cache_key] = library.libcalBuildingId
            return library.libcalBuildingId
        
        # If not found, try campus-based search (e.g., "hamilton" → Rentschler)
        # Remove "library" suffix if present
        campus_query = building_lower.replace(" library", "").strip()
        
        campus = await self._client.campus.find_first(
            where={
                "name": {"equals": campus_query, "mode": "insensitive"}
            },
            include={
                "libraries": True
            }
        )
        
        if campus and campus.libraries:
            # Return the main library for this campus
            main_library = next((lib for lib in campus.libraries if lib.isMain), None)
            if main_library:
                self._cache[cache_key] = main_library.libcalBuildingId
                return main_library.libcalBuildingId
            # Fallback to first library
            if campus.libraries:
                self._cache[cache_key] = campus.libraries[0].libcalBuildingId
                return campus.libraries[0].libcalBuildingId
        
        return None
    
    async def get_location_id(self, location_name: str) -> Optional[str]:
        """Get LibCal location ID for libraries or spaces by name.
        
        This returns the ID used for HOURS API (Image 1).
        For room reservations, use get_building_id() instead.
        
        Handles campus-based references:
        - "hamilton" or "hamilton library" → Rentschler Library hours ID
        - "middletown" or "middletown library" → Gardner-Harvey Library hours ID
        
        Args:
            location_name: Library or space name (e.g., "king", "makerspace", "hamilton", "middletown")
        
        Returns:
            LibCal location ID for hours (e.g., "8113", "11904") or None if not found
        """
        location_lower = location_name.lower().strip()
        
        # Check cache first
        cache_key = f"location_id:{location_lower}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # First check if it's a library
        library = await self._client.library.find_first(
            where={
                "OR": [
                    {"shortName": {"equals": location_lower, "mode": "insensitive"}},
                    {"name": {"contains": location_lower, "mode": "insensitive"}}
                ]
            }
        )
        
        if library and library.libcalLocationId:
            self._cache[cache_key] = library.libcalLocationId
            return library.libcalLocationId
        
        # If not found, check library spaces
        space = await self._client.libraryspace.find_first(
            where={
                "OR": [
                    {"shortName": {"contains": location_lower, "mode": "insensitive"}},
                    {"name": {"contains": location_lower, "mode": "insensitive"}}
                ]
            }
        )
        
        if space:
            self._cache[cache_key] = space.libcalLocationId
            return space.libcalLocationId
        
        # If still not found, try campus-based search
        campus_query = location_lower.replace(" library", "").strip()
        
        campus = await self._client.campus.find_first(
            where={
                "name": {"equals": campus_query, "mode": "insensitive"}
            },
            include={
                "libraries": True
            }
        )
        
        if campus and campus.libraries:
            # Return the main library's location ID for this campus
            main_library = next((lib for lib in campus.libraries if lib.isMain), None)
            if main_library and main_library.libcalLocationId:
                self._cache[cache_key] = main_library.libcalLocationId
                return main_library.libcalLocationId
            # Fallback to first library with location ID
            for lib in campus.libraries:
                if lib.libcalLocationId:
                    self._cache[cache_key] = lib.libcalLocationId
                    return lib.libcalLocationId
        
        return None
    
    async def get_building_display_name(self, building_id: str) -> str:
        """Get display name for a building by its LibCal building ID.
        
        Args:
            building_id: LibCal building ID (e.g., "2047")
        
        Returns:
            Display name (e.g., "Edgar W. King Library") or generic name
        """
        # Check cache first
        cache_key = f"building_name:{building_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        library = await self._client.library.find_first(
            where={"libcalBuildingId": building_id}
        )
        
        if library:
            self._cache[cache_key] = library.displayName
            return library.displayName
        
        return "Library"
    
    async def get_all_buildings(self) -> Dict[str, str]:
        """Get mapping of building names to LibCal building IDs.
        
        Returns:
            Dict mapping lowercase names/aliases to building IDs
            Example: {"king": "2047", "hamilton": "4792", "middletown": "4845", ...}
        """
        if "all_buildings" in self._cache:
            return self._cache["all_buildings"]
        
        # Get all campuses with their libraries
        campuses = await self._client.campus.find_many(
            include={"libraries": True}
        )
        
        building_map = {}
        for campus in campuses:
            for lib in campus.libraries:
                # Add by short name
                if lib.shortName:
                    building_map[lib.shortName.lower()] = lib.libcalBuildingId
                    building_map[f"{lib.shortName.lower()} library"] = lib.libcalBuildingId
                
                # Add by name
                building_map[lib.name.lower()] = lib.libcalBuildingId
                
                # Add common variations
                if "art" in lib.name.lower():
                    building_map["art and architecture"] = lib.libcalBuildingId
                    building_map["art & architecture"] = lib.libcalBuildingId
                elif "gardner" in lib.name.lower():
                    building_map["gardner harvey"] = lib.libcalBuildingId
                
                # Add campus-based aliases for main library of each campus
                if lib.isMain:
                    building_map[campus.name.lower()] = lib.libcalBuildingId
                    building_map[f"{campus.name.lower()} library"] = lib.libcalBuildingId
        
        self._cache["all_buildings"] = building_map
        return building_map
    
    async def get_space_building_id(self, space_name: str) -> Optional[str]:
        """Get LibCal building ID for a space (for reservations).
        
        Some spaces (like Makerspace, Special Collections) have separate reservation IDs.
        
        Args:
            space_name: Space name (e.g., "makerspace", "special collections")
        
        Returns:
            LibCal building ID for space reservations (e.g., "8269" for Makerspace)
        """
        space_lower = space_name.lower().strip()
        
        # Check cache first
        cache_key = f"space_building_id:{space_lower}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Search for space
        space = await self._client.libraryspace.find_first(
            where={
                "OR": [
                    {"shortName": {"contains": space_lower, "mode": "insensitive"}},
                    {"name": {"contains": space_lower, "mode": "insensitive"}}
                ]
            }
        )
        
        if space and space.libcalBuildingId:
            self._cache[cache_key] = space.libcalBuildingId
            return space.libcalBuildingId
        
        return None
    
    async def get_building_to_location_map(self) -> Dict[str, str]:
        """Get mapping of building IDs (for reservations) to location IDs (for hours).
        
        Returns:
            Dict mapping reservation IDs to hours IDs
            Example: {"2047": "8113", "4089": "8116", ...}
        """
        if "building_to_location" in self._cache:
            return self._cache["building_to_location"]
        
        libraries = await self._client.library.find_many()
        
        mapping = {}
        for lib in libraries:
            if lib.libcalLocationId:
                mapping[lib.libcalBuildingId] = lib.libcalLocationId
        
        self._cache["building_to_location"] = mapping
        return mapping
    
    async def get_default_building_id(self) -> str:
        """Get the default building ID (main library on main campus).
        
        Returns:
            LibCal building ID for King Library (main library)
        """
        if "default_building" in self._cache:
            return self._cache["default_building"]
        
        # Get main campus
        main_campus = await self._client.campus.find_first(
            where={"isMain": True}
        )
        
        if not main_campus:
            return "2047"  # Fallback to King Library
        
        # Get main library on main campus
        main_library = await self._client.library.find_first(
            where={
                "campusId": main_campus.id,
                "isMain": True
            }
        )
        
        if main_library:
            self._cache["default_building"] = main_library.libcalBuildingId
            return main_library.libcalBuildingId
        
        return "2047"  # Fallback
    
    async def get_campus_info(self) -> Dict[str, Dict]:
        """Get information about all campuses with their libraries.
        
        Returns:
            Dict with campus info including libraries and spaces
        """
        if "campus_info" in self._cache:
            return self._cache["campus_info"]
        
        campuses = await self._client.campus.find_many(
            include={
                "libraries": {
                    "include": {
                        "spaces": True
                    }
                }
            }
        )
        
        campus_info = {}
        for campus in campuses:
            libraries = [lib.displayName for lib in campus.libraries]
            spaces = []
            for lib in campus.libraries:
                for space in lib.spaces:
                    spaces.append(space.displayName)
            
            campus_info[campus.name] = {
                "name": campus.displayName,
                "libraries": libraries,
                "spaces": spaces
            }
        
        self._cache["campus_info"] = campus_info
        return campus_info
    
    async def get_library_contact_info(self, library_name: str = None) -> Optional[Dict[str, str]]:
        """Get contact information for a library.
        
        If no library_name is provided, returns King Library info (default).
        
        Args:
            library_name: Library name or campus name (e.g., "king", "hamilton", "art")
                         If None, defaults to King Library
        
        Returns:
            Dict with phone, address, displayName, or None if not found
            Example: {"phone": "513-529-4141", "address": "151 S. Campus Ave...", "displayName": "Edgar W. King Library"}
        """
        # Default to King Library if no name provided
        if not library_name:
            library_name = "king"
        
        # Try to get building ID first (handles campus aliases too)
        building_id = await self.get_building_id(library_name)
        
        if not building_id:
            return None
        
        # Get library by building ID
        library = await self._client.library.find_first(
            where={"libcalBuildingId": building_id}
        )
        
        if library:
            return {
                "phone": library.phone or "N/A",
                "address": library.address or "N/A",
                "displayName": library.displayName,
                "shortName": library.shortName or ""
            }
        
        return None
    
    async def is_regional_campus_ambiguous(self, query: str) -> bool:
        """Check if user mentioned 'regional' without specifying which campus.
        
        This helps determine if we need to ask for clarification.
        
        Args:
            query: User's query text
        
        Returns:
            True if user mentioned regional but didn't specify Hamilton or Middletown
        """
        query_lower = query.lower()
        
        # Check for "regional" keyword
        has_regional = any(word in query_lower for word in ["regional", "region"])
        
        # Check if they specified which campus
        has_hamilton = "hamilton" in query_lower
        has_middletown = "middletown" in query_lower
        
        # Ambiguous if they said "regional" but didn't specify which one
        return has_regional and not (has_hamilton or has_middletown)
    
    async def get_regional_campuses_info(self) -> List[Dict[str, str]]:
        """Get information about both regional campuses for clarification prompts.
        
        Returns:
            List of dicts with campus and library info
        """
        regional_campuses = await self._client.campus.find_many(
            where={"isMain": False},
            include={"libraries": True}
        )
        
        result = []
        for campus in regional_campuses:
            main_lib = next((lib for lib in campus.libraries if lib.isMain), None)
            if main_lib:
                result.append({
                    "campusName": campus.displayName,
                    "libraryName": main_lib.displayName,
                    "phone": main_lib.phone or "N/A",
                    "address": main_lib.address or "N/A"
                })
        
        return result
    
    def clear_cache(self):
        """Clear the internal cache."""
        self._cache.clear()


# Singleton instance
_location_service: Optional[LocationService] = None

def get_location_service() -> LocationService:
    """Get or create the LocationService singleton instance."""
    global _location_service
    if _location_service is None:
        _location_service = LocationService()
    return _location_service
