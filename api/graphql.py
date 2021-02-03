from ariadne import ObjectType, make_executable_schema, gql
from ariadne.asgi import GraphQL
import json, os, uuid, requests, threading, time, copy

# load schema
schemaPath =  r"https://raw.githubusercontent.com/" \
              r"coordinated-systems-lab/cube-sat/" \
              r"main/graphql/mbse-metamodel.graphql"
schemaString = requests.get(schemaPath).text
type_defs = gql(schemaString)

# load system model
modelPath = r"https://raw.githubusercontent.com/" \
            r"coordinated-systems-lab/cube-sat/" \
            r"main/graphql/earth-observation.json"
systemModel = json.loads(requests.get(modelPath).text)

# create storage for status response
status = {}
status['code'] = ""
status['message'] = ""

# create response templates
projectResponse = {}
projectResponse['status'] = status
systemModelResponse = {}
systemModelResponse['status'] = status

# create local storage for projects
projectList = []
projectList.append(systemModel['data']['cpsSystemModel']['project'])

projectStore = {}
projectStore[systemModel['data']['cpsSystemModel']['project']['id']] = \
  systemModel['data']['cpsSystemModel']

currentProjectId = ""

# setup 'transaction' handling
backupProjectList = []
backupProjectStore = {}
lock = threading.Lock()
def begin():
  global lock, currentProjectId, projectList, projectStore
  global backupProjectList, backupProjectStore
  lock.acquire()
  currentProjectId = ""
  backupProjectList = copy.deepcopy(projectList)
  backupProjectStore = copy.deepcopy(projectStore)

def commit():
  global lock, currentProjectId, projectList, projectStore
  global backupProjectList, backupProjectStore
  global projectResponse, systemModelResponse
  backupProjectList.clear()
  backupProjectStore.clear()

  projectResponse['status']['code'] = "Success"
  projectResponse['status']['message'] = ""
  projectResponse['projects'] = projectList
  systemModelResponse['status']['code'] = "Success"
  systemModelResponse['status']['message'] = ""
  if currentProjectId != "":
    systemModelResponse['cpsSystemModel'] = projectStore[currentProjectId]
  else:
    systemModelResponse['cpsSystemModel'] = None
  lock.release()

def rollback(errorCode, errorString):
  global lock, currentProjectId, projectList, projectStore
  global backupProjectList, backupProjectStore
  global projectResponse, systemModelResponse

  projectList = copy.deepcopy(backupProjectList)
  projectStore = copy.deepcopy(backupProjectStore)

  projectResponse['status']['code'] = errorCode
  projectResponse['status']['message'] = errorString
  projectResponse['projects'] = None

  systemModelResponse['status']['code'] = errorCode
  systemModelResponse['status']['message'] = errorString
  systemModelResponse['cpsSystemModel'] = None
  lock.release()

# setup Query resolvers
query = ObjectType("Query")

@query.field("cpsProjectsQuery")
def resolve_cpsProjects(obj, info):
  global projectResponse
  begin()
  commit()
  return projectResponse

@query.field("cpsSystemModelQuery")
def resolve_cpsSystemModel(obj, info, projectId):
  global currentProjectId, systemModelResponse
  begin()
  if projectId in projectStore:
    currentProjectId = projectId
    commit()
  else:
    rollback("FailureNotFound", f"ProjectId: '{projectId}' not found.")
  return systemModelResponse

# setup Mutation resolvers
mutation = ObjectType("Mutation")

@mutation.field("cpsProjectMutation")
def resolve_cpsProject(obj, info, project):
  return projectStore[project['id']]['project']

@mutation.field("cpsSystemModelMutation")
def resolve_cpsSystemModel(obj, info, projectId, cpsSystemModel):
  global currentProjectId, projectStore, systemModelResponse
  begin()
  # check for valid projectId
  if projectId not in projectStore:
    rollback("FailureNotFound", f"ProjectId: '{projectId}' not found." )
    return systemModelResponse
  else:
    currentProjectId = projectId
  # iterate through input mutation entityTypes
  for mEntityType, mEntities in cpsSystemModel.items():
    if isinstance(mEntities, list):
      # iterate through instances of entityType
      for mEntity in mEntities:
        if mEntity['operation'] == 'Delete' or mEntity['operation'] == 'Update':
          # find existing identity.id
          fEntity = {}
          fIndex = next((sIndex for sIndex, sEntity in \
            enumerate(projectStore[projectId][mEntityType]) \
              if mEntity['identity']['id'] == sEntity['identity']['id']), None)
          if fIndex != None:
            fEntity = projectStore[projectId][mEntityType].pop(fIndex)
          else:
            rollback("FailureNotFound", (
              f"EntityType: '{mEntityType}' "
              f"identity.id: '{mEntity['identity']['id']}' not found." ))
            return systemModelResponse
        if mEntity['operation'] == 'Create':
          fEntity['identity'] = {}
          fEntity['identity']['id'] = uuid.uuid4()
        if mEntity['operation'] == 'Create' or mEntity['operation'] == 'Update':
          # update mutation entity based on input
          fEntity['identity']['name'] = mEntity['identity']['name']
          fEntity['identity']['number'] = mEntity['identity']['number']

          # verify identity.name is unique
          fIndex = next((sIndex for sIndex, sEntity in \
            enumerate(projectStore[projectId][mEntityType]) \
              if fEntity['identity']['name'] == sEntity['identity']['name']), None)
          if fIndex != None:
            rollback("FailureNotUnique", (
              f"EntityType: '{mEntityType}' "
              f"identity.name: '{mEntity['identity']['name']}' not unique." ))
            return systemModelResponse

          # set attributes
          if 'attributes' in mEntity:
            for mAttrName, mAttrValue in mEntity['attributes'].items():
              if isinstance(mAttrValue, list):
                fEntity['attributes'][mAttrName].clear()
                fEntity['attributes'][mAttrName] = \
                    copy.deepcopy(mEntity['attributes'][mAttrName])
              else:
                fEntity['attributes'][mAttrName] = \
                    mEntity['attributes'][mAttrName]

          # set relationships
          if 'relations' in mEntity:
            for mRelName, mRelEntities in mEntity['relations'].items():
              for mRelEntity in mRelEntities:
                if mRelEntity['operation'] == 'Delete' or \
                    mRelEntity['operation'] == 'Update':
                  print("Creat / Delete")

          # add new / updated entity instance to projectStore
          projectStore[projectId][mEntityType].append(fEntity)
        else:
          # delete any bi-directional associations
          print("Doing delete....")
      # sort EntityType by identity.number
      projectStore[projectId][mEntityType].sort(
            key=lambda x: x['identity']['number'])

  commit()
  return systemModelResponse

# setup graphQL server from schema, queries and mutations
schema = make_executable_schema(type_defs, [query, mutation])
app = GraphQL(schema, debug=True)