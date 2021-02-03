from ariadne import ObjectType, make_executable_schema, gql
from ariadne.asgi import GraphQL
import json, os, uuid, requests

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

# create local storage for projects
projectList = []
projectList.append(systemModel['data']['cpsSystemModel']['project'])

projectStore = {}
projectStore[systemModel['data']['cpsSystemModel']['project']['id']] = \
  systemModel['data']['cpsSystemModel']

# setup Query resolvers
query = ObjectType("Query")

@query.field("cpsProjects")
def resolve_cpsProjects(obj, info):
  return projectList

@query.field("cpsSystemModel")
def resolve_cpsSystemModel(obj, info, projectId):
  return projectStore[projectId]

# setup Mutation resolvers
mutation = ObjectType("Mutation")

@mutation.field("cpsProject")
def resolve_cpsProject(obj, info, project):
  return projectStore[project['id']]['project']

@mutation.field("cpsSystemModel")
def resolve_cpsSystemModel(obj, info, projectId, cpsSystemModel):
  return projectStore[projectId]

# setup graphQL server from schema, queries and mutations
schema = make_executable_schema(type_defs, [query, mutation])
app = GraphQL(schema, debug=True)
