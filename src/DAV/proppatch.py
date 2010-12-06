#Copyright (c) 2010 Nikita Nazarenko (savant.d@gmail.com)
#
#This library is free software; you can redistribute it and/or
#modify it under the terms of the GNU Library General Public
#License as published by the Free Software Foundation; either
#version 2 of the License, or (at your option) any later version.
#
#This library is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#Library General Public License for more details.
#
#You should have received a copy of the GNU Library General Public
#License along with this library; if not, write to the Free
#Software Foundation, Inc., 59 Temple Place - Suite 330, Boston,
#MA 02111-1307, USA

import xml.dom.minidom
domimpl = xml.dom.minidom.getDOMImplementation()

import logging
import sys
import string
import urlparse
import urllib
from StringIO import StringIO

import utils
from constants import COLLECTION, OBJECT, DAV_PROPS, RT_ALLPROP, RT_PROPNAME, RT_PROP
from errors import *

log = logging.getLogger(__name__)

class PROPPATCH:
    '''
    classdocs
    '''

    def __init__(self,uri,dataclass,depth, body):
        '''
        Constructor
        '''
        self.request_type=None
        self.nsmap={}
        self.proplist={}
        self.default_ns=None
        self._dataclass=dataclass
        self._depth=str(depth)
        self._uri=uri#.rstrip('/')
        self._has_body=None    # did we parse a body?

        if dataclass.verbose:
            log.info('PROPPATCH: Depth is %s, URI is %s' % (depth, uri))

        if body:
            self.request_type, self.proplist, self.namespaces = utils.parse_propfind(body)
            self._has_body = True
            
    def createResponse(self):
        pass    