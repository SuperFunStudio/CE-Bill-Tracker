// Minimal ambient types for the one topojson-client helper we use (@types/topojson-client isn't
// installed). `feature` converts a TopoJSON object into GeoJSON we can hand to d3-geo's fitExtent.
declare module 'topojson-client' {
  import type { FeatureCollection } from 'geojson';
  export function feature(topology: unknown, object: unknown): FeatureCollection;
}
