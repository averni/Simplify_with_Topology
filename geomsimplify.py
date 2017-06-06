__author__ = 'asimmons'

import sys
import copy
import fiona
import shapely
from shapely.geometry import shape, mapping, LineString, Polygon, MultiLineString, MultiPolygon
from shapely.geometry.polygon import LinearRing
import heapq
from trianglecalculator import TriangleCalculator

# Turns on extra validation
validate = True


class GeomSimplify(object):

    def __init__(self, dictJunctions = None):
        self.junction = Junction()
        self.dictJunctions = dictJunctions

    def create_ring_from_arcs(self, arcList):
        ringPoints = []

        for arc in arcList:
            arcPoints = arc.coords;
            if len(ringPoints) == 0:
                ringPoints.extend(arcPoints)
            else:
                if validate:

                    last = self.junction.quantitize(ringPoints[-1])
                    first = self.junction.quantitize(arcPoints[0])
                    if last[0] != first[0] or last[1] != first[1]:
                        raise ValueError('arcList does not form a ring.')
                ringPoints.extend(arcPoints[1:])

        # If the there are not enough points to make a ring, return None
        if len(ringPoints) < 3:
            return None

        return LinearRing(ringPoints)

    def simplify_line_topology(self, line, threshold):
        if not self.dictJunctions:
            return self.simplify_line(line, threshold)

        lineList = self.junction.cut_line_by_junctions(line, self.dictJunctions)
        simplifiedLines = []
        for line in lineList:
            simplifiedLines.append(self.simplify_line(line, threshold))

        if len(simplifiedLines) == 1:
            return simplifiedLines[0]
        else:
            return MultiLineString(simplifiedLines)


    def simplify_line(self, line, threshold):
        """

        Simplifies LineString objects. Returns a shapely LineString obj.

        Note: unlike rings, we need to keep beginning and end points static throughout the simplification process

        """

        # Build list of Triangles from the line points
        triangleArray = []
        ## each triangle contains an index and a point (x,y)
        # handle line 'interior' (i.e. the vertices
        #  between start and end) first -- explicitly
        # defined using the below slice notation
        # i.e. [1:-1]
        for index, point in enumerate(line.coords[1:-1]):
            triangleArray.append(TriangleCalculator(point, index))

        # then create start/end points separate from the triangleArray (meaning
        # we cannot have the start/end points included in the heap sort)
        startIndex = 0
        endIndex = len(line.coords)-1
        startTriangle = TriangleCalculator(line.coords[startIndex], startIndex)
        endTriangle = TriangleCalculator(line.coords[endIndex], endIndex)

        # Hook up triangles with next and prev references (doubly-linked list)
        # NOTE: linked list are composed of nodes, which have at
        # least one link to another node (and this is a doubly-linked list..pointing at
        # both our prevTriangle & our nextTriangle)
        # NOTE: in this code block the 'triangle' is our 'triangle node'

        for index, triangle in enumerate(triangleArray):
            # set prevIndex to be the adjacent point to index
            prevIndex = index - 1
            nextIndex = index + 1

            if prevIndex >= 0:
                triangle.prevTriangle = triangleArray[prevIndex]
            else:
                triangle.prevTriangle = startTriangle

            if nextIndex < len(triangleArray):
                triangle.nextTriangle = triangleArray[nextIndex]
            else:
                triangle.nextTriangle = endTriangle

        # Build a min-heap from the TriangleCalculator list
        # print "heapify"
        heapq.heapify(triangleArray)


        # Simplify steps...


        # Note: in contrast
        # to our function 'simplify_ring'
        # we can allow our array to go down to 0 and STILL have a valid line
        # because we will still have the start and end points
        while len(triangleArray) > 0:
            # if the smallest triangle is greater than the threshold, we can stop
            # i.e. loop to point where the heap head is >= threshold
            if triangleArray[0].calcArea() >= threshold:
                #print "break"
                break
            else:
                # print statement for debugging - prints area's and coords of deleted/simplified pts
                #print "simplify...triangle area's and their corresponding points that were less then the threshold"
                #print "area = " + str(triangleArray[0].calcArea()) + ", point = " + str(triangleArray[0].point)
                prev = triangleArray[0].prevTriangle
                next = triangleArray[0].nextTriangle
                prev.nextTriangle = next
                next.prevTriangle = prev
                # This has to be done after updating the linked list
                # in order for the areas to be correct when the
                # heap re-sorts
                heapq.heappop(triangleArray)


        # Create an list of indices from the triangleRing heap
        indexList = []
        for triangle in triangleArray:
            # add 1 b/c the triangle array's first index is actually the second point
            indexList.append(triangle.ringIndex + 1)
        # Append start and end points back into the array
        indexList.append(startTriangle.ringIndex)
        indexList.append(endTriangle.ringIndex)

        # Sort the index list
        indexList.sort()

        # Create a new simplified ring
        simpleLine = []
        for index in indexList:
            simpleLine.append(line.coords[index])

        # Convert list into LineString
        simpleLine = LineString(simpleLine)

        return simpleLine

    def simplify_multiline_topology(self, mline, threshold):
        if not self.dictJunctions:
            return self.simplify_multiline(mline, threshold)

        mlineArray = self.junction.cut_mline_by_junctions(mline, self.dictJunctions)
        simplifiedShapes = []
        for mline in mlineArray:
            simplifiedShapes.append(self.simplify_multiline(mline, threshold))

        linesList = []
        for mline in simplifiedShapes:
            for line in mline.geoms:
                linesList.append(line)

        return MultiLineString(linesList)

    def simplify_multiline(self, mline, threshold):
        """
        Simplifies MultiLineStrings. Returns a shapely MultiLineString obj.

        """
         # break MultiLineString into lines
        lineList = mline.geoms
        simpleLineList = []

        # call simplify_line on each
        for line in lineList:
            simpleLine = self.simplify_line(line, threshold)
            #if not none append to list
            if simpleLine:
                simpleLineList.append(simpleLine)

        # check that line count > 0, otherwise return None
        if not simpleLineList:
            return None

        # put back into multilinestring
        return MultiLineString(simpleLineList)

    def simplify_polygon_topology(self, poly, threshold):
        if self.dictJunctions:
            cutPolygonTuple = self.junction.cut_polygon_by_junctions(poly, self.dictJunctions)
            arcList = cutPolygonTuple[0]
            originalPolygon = cutPolygonTuple[1]

            if arcList is None: # No junctions on polygon exterior ring
                simpleExtRing = GeomSimplify.simplify_ring(poly.exterior, threshold)
            else:
                simpleArcList = []
                num_junctions = len(arcList)
                for arc in arcList:

                    # TODO find joint threshold

                    simpleArc = self.simplify_line(arc, threshold, )
                    simpleArcList.append(simpleArc)

                # Stitch the arcs back together into a ring
                simpleExtRing = self.create_ring_from_arcs(simpleArcList)
        else:
            # Get exterior ring
            simpleExtRing = GeomSimplify.simplify_ring(poly.exterior, threshold)

        # If the exterior ring was removed by simplification, return None
        if simpleExtRing is None:
            return None

        simpleIntRings = []
        for ring in poly.interiors:
            simpleRing = GeomSimplify.simplify_ring(ring, threshold)
            if simpleRing is not None:
                simpleIntRings.append(simpleRing)

        #TODO
        # Check for interior rings that have points outside the exterior ring,

        # Check if more than one interior ring touches the exterior ring

        return shapely.geometry.Polygon(simpleExtRing, simpleIntRings)

    def simplify_multipolygon_topology(self, mpoly, threshold):
        # break multipolygon into polys
        polyList = mpoly.geoms
        simplePolyList = []

        # call simplify_polygon() on each
        for poly in polyList:
            simplePoly = self.simplify_polygon_topology(poly, threshold)
            #if not none append to list
            if simplePoly:
                simplePolyList.append(simplePoly)

        # check that polygon count > 0, otherwise return None
        if not simplePolyList:
            return None

        # put back into multipolygon
        return MultiPolygon(simplePolyList)

    @staticmethod
    def rotate_ring(ring, index):
        # Validate index
        if index < 0 or index > len(ring.coords) - 2:
            raise ValueError('Invalid index in rotate_ring: ' + repr(index))

        points = []
        for point in ring.coords[index:-1]:
            points.append(point)
        for point in ring.coords[:index]:
            points.append(point)

        newRing = LinearRing(points)

        #Validate
        if len(newRing.coords) != len(ring.coords):
            raise ValueError('Failed to rotate ring.')

        return newRing

    @staticmethod
    def simplify_ring(ring, threshold, minimumPoints = 2):

        # Build list of TriangleCalculators
        triangleRing = []
        ## each triangle contains an index and a point (x,y)
        ## because rings have a point on top of a point
        ## we are skipping the last point by using slice notation[:-1]
        ## *i.e. 'a[:-1]' # everything except the last item*
        for index, point in enumerate(ring.coords[:-1]):
            triangleRing.append(TriangleCalculator(point, index))

        # Hook up triangles with next and prev references (doubly-linked list)
        for index, triangle in enumerate(triangleRing):
            # set prevIndex to be the adjacent point to index
            # these steps are necessary for dealing with
            # closed rings
            prevIndex = index - 1
            if prevIndex < 0:
                # if prevIndex is less than 0, then it means index = 0, and
                # the prevIndex is set to last value in the index
                # (i.e. adjacent to index[0])
                prevIndex = len(triangleRing) - 1
            # set nextIndex adjacent to index
            nextIndex = index + 1
            if nextIndex == len(triangleRing):
                # if nextIndex is equivalent to the length of the array
                # set nextIndex to 0
                nextIndex = 0
            triangle.prevTriangle = triangleRing[prevIndex]
            triangle.nextTriangle = triangleRing[nextIndex]

        # Build a min-heap from the TriangleCalculator list
        heapq.heapify(triangleRing)

        # Simplify
        while len(triangleRing) > minimumPoints:
            # if the smallest triangle is greater than the threshold, we can stop
            # i.e. loop to point where the heap head is >= threshold

            if triangleRing[0].calcArea() >= threshold:
                break
            else:
                prev = triangleRing[0].prevTriangle
                next = triangleRing[0].nextTriangle
                prev.nextTriangle = next
                next.prevTriangle = prev
                # This has to be done after updating the linked list
                # in order for the areas to be correct when the
                # heap re-sorts
                heapq.heappop(triangleRing)

        # Handle case where we've removed too many points for the ring to be a polygon
        if len(triangleRing) < 3:
            return None

        # Create an list of indices from the triangleRing heap
        indexList = []
        for triangle in triangleRing:
            indexList.append(triangle.ringIndex)

        # Sort the index list
        indexList.sort()

        # Create a new simplified ring
        simpleRing = []
        for index in indexList:
            simpleRing.append(ring.coords[index])

        # Convert list into LinearRing
        simpleRing = LinearRing(simpleRing)

        # print statements for debugging to check if points are being reduced...
        #print "Starting size: " + str(len(ring.coords))
        #print "Ending size: " + str(len(simpleRing.coords))

        return simpleRing

class Junction(object):
    # default quantization factor is 1
    quantitizationFactor = (0.001,0.001)

    def set_quantitization_factor(self, quantValue):
        self.quantitizationFactor = (quantValue, quantValue)

    def quantitize(self, point):
        # the default quantization factor is 1
        # Divide by quantitiztion factor, round(int), multiply by quantitization factor
        x_quantitized = int(round(point[0]/self.quantitizationFactor[0])) * self.quantitizationFactor[0]
        y_quantitized = int(round(point[1]/self.quantitizationFactor[1])) * self.quantitizationFactor[1]

        return (x_quantitized,y_quantitized)

    def append_junctions(self, dictJunctions, dictNeighbors, pointsList):
        """
        Builds a global dictionary of all the junctions and neighbors found in a
        single geometry within a shapefile. It determines if a point is a junction based on if it shares the same
        point AND has different neighbors.
        """
        # updates dictJunctions & dictNeighbors
        for index, point in enumerate(pointsList):
            quant_point = self.quantitize(point)
            quant_neighbors = []
            # append the previous neighbor
            if index - 1 > 0:
                quant_neighbors.append(self.quantitize(pointsList[index - 1]))
            # append the next neighbor
            if index + 1 < len(pointsList):
                quant_neighbors.append(self.quantitize(pointsList[index + 1]))

            # check if point is in dictNeighbors, if it is
            # check if the neighbors are equivalent to what
            # is already in there, if not equiv. append to
            # dictJunctions

            if quant_point in dictNeighbors:
                # check if neighbors are equivalent
                if set(dictNeighbors[quant_point]) != set(quant_neighbors):
                    dictJunctions[quant_point] = 1
            else:
                # Otherwise, add to neighbors
                dictNeighbors[quant_point] = quant_neighbors

    def find_all_junctions(self, inFile, dictJunctions):
        """
        Builds a global dictionary of all the junctions and neighbors found in a shapefile.
        """

        # declare dictNeighbors as a global
        # key = checked quantitized points, value = array of quantitized neighbors
        dictNeighbors = {}

        # loop over each
        with fiona.open(inFile, 'r') as input:

            # read shapely geometries from file
            for myGeom in input:
                myShape = shape(myGeom['geometry'])

                if isinstance(myShape, LineString):
                    self.find_junctions_line(myShape, dictJunctions, dictNeighbors)

                elif isinstance(myShape, MultiLineString):
                    self.find_junctions_mline(myShape, dictJunctions, dictNeighbors)

                elif isinstance(myShape, Polygon):
                    self.find_junctions_polygon(myShape, dictJunctions, dictNeighbors)

                elif isinstance(myShape, MultiPolygon):
                    self.find_junctions_mpolygon(myShape, dictJunctions, dictNeighbors)

                else:
                    raise ValueError('Unhandled geometry type: ' + repr(myShape.type))


    def find_junctions_line(self, myShape, dictJunctions, dictNeighbors):

        pointsLineList = list(myShape.coords)

        self.append_junctions(dictJunctions, dictNeighbors, pointsLineList)


    def find_junctions_mline(self, myShape, dictJunctions, dictNeighbors):
        for line in myShape.geoms:
            self.find_junctions_line(line, dictJunctions, dictNeighbors)

    def find_junctions_polygon(self, myShape, dictJunctions, dictNeighbors):
        if validate:
            if not isinstance(myShape, Polygon):
                raise ValueError('Non-Polygon passed to find_junctions_polygon: ' + repr(myShape.type))

        pointsList = list(myShape.exterior.coords[:-1])
        self.append_junctions(dictJunctions, dictNeighbors, pointsList)

        # Validate that interior rings have no junctions
        if validate:
            countJunctions = len(dictJunctions)
            for ring in myShape.interiors:
                self.append_junctions(dictJunctions, dictNeighbors, list(ring.coords[:-1]))
                if len(dictJunctions) != countJunctions:
                    raise ValueError('Junction found on interior ring')


    def find_junctions_mpolygon(self, myShape, dictJunctions, dictNeighbors):
        for polygon in myShape.geoms:
            self.find_junctions_polygon(polygon, dictJunctions, dictNeighbors)


    def cut_line_by_junctions(self, myShape, dictJunctions):
        """
        Returns Arcs from LineStrings.

        AN arc is a LineString between two junctions (note: junctions are end/start points & cannot be simplified)
        IF a LineString has no found junctions then it is written as is into a list of lists.

        Returns 'arcs', LineString objects. By definiton a linestrings must have at least 2 points.

        arcs = List of list (all of the [arc]'s found in a single line segment)

        arc = a single arc being built from a linestring (arc ends when a junction is found)
        """

        arcs = []
        arc = []
        pointsLineList = list(myShape.coords)

        # split lines into arcs by junctions
        for point in pointsLineList:
            # quantitize the point
            # self.quantitize(point)
            quant_pt = self.quantitize(point)
            # add the point to the 'arc' list till a
            # junction point is identified
            arc.append(point)
            length_of_arc = len(arc)
            #print length_of_arc
            if quant_pt in dictJunctions and length_of_arc >= 2:
                # if the junction is in the
                # list add to arcs
                arcs.append(arc)
                arc = [point]
        # make sure you have at least 2 pt for line
        # also ensures that if the starting point
        # of a line is a junction the line
        # cannot be cut there (because it would be an invalid line, < 2 pts)
        if len(arc) > 1:
            arcs.append(arc)
        # create a shapely Linestring object of arcs
        arcsLine = [LineString(ar) for ar in arcs]
        return arcsLine

    def cut_mline_by_junctions(self, myShape, dictJunctions):
        """
        Returns MultiLineStrings divided as arcs at junction points from MultiLineStrings.

        lineList = shapely geom collection, Multilinestring
        """

        lineList = myShape.geoms
        junctionedLines = []
        multiJunctionedLines = []
        for line in lineList:
            # breaks the MultiLine Geom collection into LineStrings
            # finds the junctions in the LineStrings and cuts them
            # accordingly
            junctionedLines.append(self.cut_line_by_junctions(line, dictJunctions))
        for cut_mline in junctionedLines:
            # writes the re-junctioned Linestrings back as a MultiLineString
            multiJunctionedLines.append(MultiLineString(cut_mline))

        #multiLineArc = MultiLineString(multiJunctionedLines)

        return multiJunctionedLines

    def cut_ring_by_junctions(self, ring, dictJunctions):
        #Verify a ring was passed to function
        if validate:
            if ring.coords[0] != ring.coords[-1]:
                raise ValueError('Invalid ring passed to cut_ring_by_junctions: ' + repr(ring.coords))

        # Identify junction points
        junctionPointIndices = []
        for index, point in enumerate(ring.coords[:-1]):
            quant_pt = self.quantitize(point)
            if quant_pt in dictJunctions:
                junctionPointIndices.append(index)

        # Rotate the ring to the first junction point
        if len(junctionPointIndices) > 0:
            ring = GeomSimplify.rotate_ring(ring, junctionPointIndices[0])

        # If there are no junctions on ring just return None
        if len(junctionPointIndices) == 0:
            return None

        # Cut the ring into lines if there are junctions
        arcsList = self.cut_line_by_junctions(ring, dictJunctions)
        return arcsList

    def cut_polygon_by_junctions(self, myShape, dictJunctions):
        if validate:
            if not isinstance(myShape, Polygon):
                raise ValueError('Non-Polygon passed to cut_polygon_by_junctions: ' + repr(myShape.type))

        exteriorRing = myShape.exterior
        interiorRings = myShape.interiors

        # Count junctions on exterior ring
        junctionCountExtRing = self.count_junctions_in_points_list(exteriorRing.coords, dictJunctions)

        # If there are at least 1, but fewer than 3 junctions on the exterior ring
        # we need to add new 'junctions' to make sure we don't simplify below 3 points
        # New junctions are necessary so we don't simplify that point for any bordering polygons
        if junctionCountExtRing > 0 and junctionCountExtRing < 3:
            junctionsToAdd = 3 - junctionCountExtRing
            self.add_junctions_to_ring(exteriorRing, junctionsToAdd, dictJunctions)

        # InteriorRings should have no junctions, so only cut the exterior ring
        cutExteriorRing = self.cut_ring_by_junctions(exteriorRing, dictJunctions)

        # Validate that there are no junctions on the interior rings
        if validate:
            for ring in interiorRings:
                for point in ring.coords:
                    if self.quantitize(point) in dictJunctions:
                        raise ValueError('Interior ring has a junction point: ' + repr(point))

        # Return a tuple containing the cut exterior ring, and the original shape
        return (cutExteriorRing, myShape)


    def cut_mpolygon_by_junctions(self, myShape, dictJunctions):
        if validate:
            if not isinstance(myShape, MultiPolygon):
                raise ValueError('Non-MultiPolygon passed to cut_mpolygon_by_junctions: ' + repr(myShape.type))

        cutMpolyList = []
        for polygon in myShape.geoms:
            cutMpolyList.append(self.cut_polygon_by_junctions(myShape, dictJunctions))

        return cutMpolyList

    def count_junctions_in_points_list(self, pointsList, dictJunctions):
        junctionPoints = []
        for point in pointsList:
            qp = self.quantitize(point)
            if qp in dictJunctions and qp not in junctionPoints:
                junctionPoints.append(qp)
        return len(junctionPoints)


    def add_junctions_to_ring(self, ring, junctionsToAdd, dictJunctions):
        # Copy ring to temporary
        tempRing = copy.copy(ring)

        # Simplify the ring to (junctionsToAdd + 2) points
        simpleRing = GeomSimplify.simplify_ring(tempRing, sys.maxsize, minimumPoints=junctionsToAdd+2)

        # Add the ring points to dictJunctions
        for point in simpleRing.coords:
            quant_point = self.quantitize(point)
            if quant_point not in dictJunctions:
                dictJunctions[quant_point] = 0
                # Using a 0 instead of a 1 to distinguish this type of of junction from
                # the ones calculated by append_junctions