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
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
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
            main_library = next((lib for lib in campus.libraries if lib.isMain), None)
            if main_library:
                self._cache[cache_key] = main_library.libcalBuildingId
                return main_library.libcalBuildingId
            if campus.libraries:
                self._cache[cache_key] = campus.libraries[0].libcalBuildingId
                return campus.libraries[0].libcalBuildingId
        
        return None
    
    async def get_location_id(self, location_name: str) -> Optional[str]:
        """Get LibCal location ID for libraries or spaces by name."""
        location_lower = location_name.lower().strip()
        
        cache_key = f"location_id:{location_lower}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
        # Special handling for known spaces (prevent ambiguous matches)
        space_mappings = {
            "makerspace": ["makerspace", "maker space"],
            "special collections": ["special collections", "special collection", "university archives"],
        }
        
        for canonical_name, aliases in space_mappings.items():
            if any(alias in location_lower for alias in aliases):
                space = await self._client.libraryspace.find_first(
                    where={
                        "OR": [
                            {"shortName": {"equals": canonical_name.title(), "mode": "insensitive"}},
                            {"name": {"contains": canonical_name, "mode": "insensitive"}}
                        ]
                    }
                )
                if space:
                    self._cache[cache_key] = space.libcalLocationId
                    return space.libcalLocationId
        
        # First check if it's a library
        library = await self._client.library.find_first(
            where={
                "OR": [
                    {"shortName": {"contains": location_lower, "mode": "insensitive"}},
                    {"name": {"contains": location_lower, "mode": "insensitive"}}
                ]
            }
        )
        
        if library and library.libcalLocationId:
            self._cache[cache_key] = library.libcalLocationId
            return library.libcalLocationId
        
        # Check library spaces
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
        
        # Try campus-based search
        campus_query = location_lower.replace(" library", "").strip()
        campus = await self._client.campus.find_first(
            where={"name": {"equals": campus_query, "mode": "insensitive"}},
            include={"libraries": True}
        )
        
        if campus and campus.libraries:
            main_library = next((lib for lib in campus.libraries if lib.isMain), None)
            if main_library and main_library.libcalLocationId:
                self._cache[cache_key] = main_library.libcalLocationId
                return main_library.libcalLocationId
            for lib in campus.libraries:
                if lib.libcalLocationId:
                    self._cache[cache_key] = lib.libcalLocationId
                    return lib.libcalLocationId
        
        return None
    
    async def get_building_display_name(self, building_id: str) -> str:
        """Get display name for a building by its LibCal building ID.
        
        Args:
            building_id: LibCal building ID
        
        Returns:
            Display name of the building
        """
        cache_key = f"building_name:{building_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
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
            Dict mapping library names/aliases to their building IDs
        """
        if "all_buildings" in self._cache:
            return self._cache["all_buildings"]
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
        # Get all libraries from database
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
            LibCal building ID for space reservations or None if not found
        """
        space_lower = space_name.lower().strip()
        
        # Check cache first
        cache_key = f"space_building_id:{space_lower}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
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
            Dict mapping building IDs to location IDs
        """
        if "building_to_location" in self._cache:
            return self._cache["building_to_location"]
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
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
            LibCal building ID for King Library (default)
        """
        if "default_building" in self._cache:
            return self._cache["default_building"]
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
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
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
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
        """Get contact information for a library."""
        if not library_name:
            library_name = "king"
        
        search_name = library_name.lower().strip()
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
        # Direct DB query - search by short name or display name
        library = await self._client.library.find_first(
            where={
                "OR": [
                    {"shortName": {"equals": search_name, "mode": "insensitive"}},
                    {"name": {"contains": search_name, "mode": "insensitive"}}
                ]
            }
        )
        
        # If not found by library name, try campus-based search
        if not library:
            campus_query = search_name.replace(" library", "").strip()
            campus = await self._client.campus.find_first(
                where={"name": {"equals": campus_query, "mode": "insensitive"}},
                include={"libraries": True}
            )
            if campus and campus.libraries:
                library = next((lib for lib in campus.libraries if lib.isMain), None)
                if not library:
                    library = campus.libraries[0] if campus.libraries else None
        
        if library:
            return {
                "phone": library.phone or "N/A",
                "address": library.address or "N/A",
                "website": library.website or "https://www.lib.miamioh.edu/",
                "displayName": library.displayName,
                "shortName": library.shortName or ""
            }
        
        return None
    
    async def get_space_location_info(self, space_name: str) -> Optional[Dict[str, str]]:
        """Get location info for a library space (Makerspace, Special Collections, etc.).
        
        Queries LibrarySpace table and joins with parent Library to compose
        a complete location description including building location within the library.
        
        Args:
            space_name: Space name (e.g., "makerspace", "special collections")
            
        Returns:
            Dict with displayName, location, address, phone, website, or None if not a space
        """
        if not space_name:
            return None
        
        search_name = space_name.lower().strip()
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
        # Query LibrarySpace with parent Library included
        space = await self._client.libraryspace.find_first(
            where={
                "OR": [
                    {"shortName": {"contains": search_name, "mode": "insensitive"}},
                    {"name": {"contains": search_name, "mode": "insensitive"}}
                ]
            },
            include={"library": True}
        )
        
        if not space:
            return None
        
        parent_library = space.library
        building_location = space.buildingLocation or ""
        parent_name = parent_library.displayName if parent_library else "King Library"
        parent_address = parent_library.address if parent_library else "351 S. Campus Ave, Oxford, OH 45056"
        
        # Use space-level phone/email if available
        # Only fall back to parent library phone for physical spaces (those with a buildingLocation)
        if space.phone:
            phone = space.phone
        elif building_location:
            phone = parent_library.phone if parent_library else "(513) 529-4141"
        else:
            phone = None
        email = space.email or None
        
        # Compose location string: e.g., "Third floor, King Library"
        if building_location:
            location = f"{building_location}, {parent_name}"
        else:
            location = parent_name
        
        return {
            "displayName": space.displayName or space.name,
            "location": location,
            "address": parent_address,
            "phone": phone,
            "email": email,
            "website": space.website or parent_library.website if parent_library else "https://www.lib.miamioh.edu/"
        }
    
    async def get_library_website(self, library_name: str = None) -> str:
        """Get website URL for a library or space.
        
        Args:
            library_name: Library name, campus name, or space name
                         (e.g., "king", "hamilton", "middletown", "art", "makerspace", "special collections")
                         If None, defaults to King Library
        
        Returns:
            Website URL string
        """
        # Default to King Library if no name provided
        if not library_name:
            return "https://www.lib.miamioh.edu/"
        
        # Check cache first
        cache_key = f"website:{library_name.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Ensure database is connected
        if not self._client.is_connected():
            await self._client.connect()
        
        # First check if it's a space (Makerspace, Special Collections)
        space = await self._client.libraryspace.find_first(
            where={
                "OR": [
                    {"shortName": {"contains": library_name.lower(), "mode": "insensitive"}},
                    {"name": {"contains": library_name.lower(), "mode": "insensitive"}}
                ]
            }
        )
        
        if space and space.website:
            self._cache[cache_key] = space.website
            return space.website
        
        # If not a space, try to get building ID (handles campus aliases too)
        building_id = await self.get_building_id(library_name)
        
        if not building_id:
            return "https://www.lib.miamioh.edu/"
        
        # Get library by building ID
        library = await self._client.library.find_first(
            where={"libcalBuildingId": building_id}
        )
        
        if library and library.website:
            self._cache[cache_key] = library.website
            return library.website
        
        # Fallback to main library website
        return "https://www.lib.miamioh.edu/"
    
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
            List of dicts with campus info: [{"name": "Hamilton", "library": "Rentschler Library"}, ...]
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
    
    async def validate_library_for_rooms(self, building_name: str) -> tuple[bool, str, str]:
        """Validate if a library name is valid for room reservations.
        
        Args:
            building_name: Library name to validate
        
        Returns:
            Tuple of (is_valid, building_id_or_error, normalized_name)
        """
        if not building_name:
            return False, "Please specify a library name.", ""
        
        building_lower = building_name.lower().strip()
        
        # Try to get building ID
        building_id = await self.get_building_id(building_lower)
        
        if building_id:
            # Get display name
            display_name = await self.get_building_display_name(building_id)
            return True, building_id, display_name
        
        # Not found - get list of valid libraries
        libraries = await self._client.library.find_many(
            where={"libcalBuildingId": {"not": None}}
        )
        
        valid_names = [lib.displayName for lib in libraries if lib.libcalBuildingId]
        valid_list = "\n".join([f"• {name}" for name in valid_names])
        
        error_msg = f"'{building_name}' is not a valid library for room reservations. Study rooms are available at:\n{valid_list}\n\nPlease specify one of these libraries."
        
        return False, error_msg, ""


# Singleton instance
_location_service: Optional[LocationService] = None

def get_location_service() -> LocationService:
    """Get or create the LocationService singleton instance."""
    global _location_service
    if _location_service is None:
        _location_service = LocationService()
    return _location_service
